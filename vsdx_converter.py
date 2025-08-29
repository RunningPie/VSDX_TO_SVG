import zipfile
import xml.etree.ElementTree as ET
import re
import math

class VsdxToSvgConverter:
    """
    Enhanced VSDX to SVG converter with proper style inheritance,
    complete style property parsing, and CSS class generation.
    """

    def __init__(self, vsdx_file_path):
        self.vsdx_file_path = vsdx_file_path
        self.namespaces = {
            'v': 'http://schemas.microsoft.com/office/visio/2012/main',
            'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
        }
        
        # Page properties with better scaling
        self.page_width = 1190.55   # Standard A4 landscape width in pixels
        self.page_height = 841.89   # Standard A4 landscape height in pixels
        self.visio_to_svg_scale = 72.0  # Scale factor for coordinate conversion
        
        # Data structures
        self.masters = {}
        self.shapes = {}
        self.page_shapes = []
        self.styles = {}
        self.page_styles = {}
        self.colors = {}
        self.css_classes = {}
        self.class_counter = 1

        # Theme-related data structures
        self.theme_properties = {}  # Dynamic theme style sheet properties
        self.theme_colors = {}      # Theme color scheme
        self.theme_fonts = {}       # Theme font scheme
        self.theme_effects = {}     # Theme effect scheme
        
        # Zip file reference
        self.zf = None

    def _get_xml_tree(self, zip_file, xml_path):
        """Reads and parses an XML file from the zip archive."""
        try:
            with zip_file.open(xml_path) as xml_file:
                return ET.parse(xml_file)
        except KeyError:
            print(f"Warning: XML file not found at {xml_path}")
            return None

    def _parse_colors(self, zf):
        """Parse color definitions from document.xml."""
        print("Parsing colors...")
        
        document_tree = self._get_xml_tree(zf, 'visio/document.xml')
        if not document_tree:
            return
        
        for color_elem in document_tree.findall('.//v:ColorEntry', self.namespaces):
            color_id = color_elem.get('IX')
            rgb_value = color_elem.get('RGB')
            if color_id and rgb_value:
                try:
                    if rgb_value.startswith('#'):
                        self.colors[color_id] = rgb_value
                    else:
                        # Convert numeric RGB to hex
                        rgb_int = int(rgb_value)
                        hex_color = f"#{rgb_int:06x}"
                        self.colors[color_id] = hex_color
                except:
                    self.colors[color_id] = '#000000'

    def _parse_styles(self, zf):
        """Parse style definitions from document.xml with complete property support."""
        print("Parsing styles...")
        
        document_tree = self._get_xml_tree(zf, 'visio/document.xml')
        if not document_tree:
            return
        
        for style_elem in document_tree.findall('.//v:StyleSheet', self.namespaces):
            style_id = style_elem.get('ID')
            name = style_elem.get('NameU', 'Unknown')
            
            if style_id:
                style_data = {
                    'id': style_id,
                    'name': name,
                    'properties': {}
                }
                
                # Parse ALL style properties, evaluating themed values
                for cell_elem in style_elem.findall('v:Cell', self.namespaces):
                    cell_name = cell_elem.get('N')
                    cell_value = self._evaluate_themed_cell(cell_elem)
                    style_data['properties'][cell_name] = cell_value

                self.styles[style_id] = style_data
                print(f"  - Parsed Style {style_id}: {name}")

    def _parse_page_styles(self, zf):
        """Parse page-level styles from page XML files."""
        print("Parsing page styles...")
        
        # Parse page styles from masters
        masters_tree = self._get_xml_tree(zf, 'visio/masters/masters.xml')
        if masters_tree:
            for master in masters_tree.findall('v:Master', self.namespaces):
                page_sheet = master.find('v:PageSheet', self.namespaces)
                if page_sheet is not None:
                    master_id = master.get('ID')
                    page_style_data = self._parse_page_sheet_properties(page_sheet)
                    self.page_styles[f"master_{master_id}"] = page_style_data
        
        # Parse page styles from main page
        page_xml_path = 'visio/pages/page1.xml'
        try:
            page_rels_tree = self._get_xml_tree(zf, 'visio/pages/_rels/pages.xml.rels')
            if page_rels_tree is not None:
                rel_ns = {'rel': 'http://schemas.openxmlformats.org/package/2006/relationships'}
                first_rel = page_rels_tree.find('.//rel:Relationship', rel_ns)
                if first_rel is not None:
                    target = first_rel.get('Target')
                    if target:
                        page_xml_path = f'visio/pages/{target}'
        except:
            pass

        page_tree = self._get_xml_tree(zf, page_xml_path)
        if page_tree:
            page_sheet = page_tree.find('.//v:PageSheet', self.namespaces)
            if page_sheet is not None:
                page_style_data = self._parse_page_sheet_properties(page_sheet)
                self.page_styles['page'] = page_style_data

    def _parse_page_sheet_properties(self, page_sheet_elem):
        """Parse properties from a PageSheet element."""
        properties = {}
        for cell_elem in page_sheet_elem.findall('v:Cell', self.namespaces):
            cell_name = cell_elem.get('N')
            cell_value = self._evaluate_themed_cell(cell_elem)
            properties[cell_name] = cell_value
        return properties

    def _parse_themed_values(self, zf):
        """Parse dynamic theme style sheet and theme components."""
        print("Parsing theme components...")

        document_tree = self._get_xml_tree(zf, 'visio/document.xml')
        if not document_tree:
            return

        # Find dynamic theme style sheet (NameU="Theme")
        for style_elem in document_tree.findall('.//v:StyleSheet', self.namespaces):
            name_u = style_elem.get('NameU', '')
            if name_u == 'Theme':
                theme_id = style_elem.get('ID')
                print(f"  - Found dynamic theme style sheet: {theme_id}")

                # Parse theme properties
                theme_properties = {}
                for cell_elem in style_elem.findall('v:Cell', self.namespaces):
                    cell_name = cell_elem.get('N')
                    cell_value = cell_elem.get('V', '0')
                    theme_properties[cell_name] = cell_value

                self.theme_properties = theme_properties
                break

        # Look for theme XML part if it exists
        try:
            theme_tree = self._get_xml_tree(zf, 'visio/theme/theme1.xml')
            if theme_tree:
                self._parse_theme_xml(theme_tree)
        except:
            pass  # Theme XML part might not exist

    def _parse_theme_xml(self, theme_tree):
        """Parse theme XML part for additional theme information."""
        print("  - Parsing theme XML part")

        # Parse Office theme components if present
        # This handles the ISO/IEC29500 theme format
        root = theme_tree.getroot()

        # Look for themeElements (Office theme format)
        theme_elements = root.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}themeElements')
        if theme_elements is not None:
            # Parse color scheme
            clr_scheme = theme_elements.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}clrScheme')
            if clr_scheme is not None:
                self._parse_color_scheme(clr_scheme)

            # Parse font scheme
            font_scheme = theme_elements.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}fontScheme')
            if font_scheme is not None:
                self._parse_font_scheme(font_scheme)

            # Parse effect scheme
            fmt_scheme = theme_elements.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}fmtScheme')
            if fmt_scheme is not None:
                self._parse_effect_scheme(fmt_scheme)

    def _parse_color_scheme(self, clr_scheme):
        """Parse Office theme color scheme."""
        # Parse the 12 standard theme colors + accent colors
        color_mapping = {
            'dk1': 'lt1', 'dk2': 'lt2', 'lt1': 'dk1', 'lt2': 'dk2',
            'accent1': 'accent1', 'accent2': 'accent2', 'accent3': 'accent3',
            'accent4': 'accent4', 'accent5': 'accent5', 'accent6': 'accent6',
            'hlink': 'hlink', 'folHlink': 'folHlink'
        }

        for color_elem in clr_scheme:
            color_name = color_elem.tag.split('}')[-1]  # Remove namespace
            if color_name in color_mapping:
                # Extract color value (this is simplified - real implementation would parse RGB values)
                self.theme_colors[color_mapping[color_name]] = self._extract_color_value(color_elem)

    def _parse_font_scheme(self, font_scheme):
        """Parse Office theme font scheme."""
        # Parse major and minor font sets
        major_font = font_scheme.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}majorFont')
        minor_font = font_scheme.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}minorFont')

        if major_font is not None:
            self.theme_fonts['major'] = self._extract_font_info(major_font)
        if minor_font is not None:
            self.theme_fonts['minor'] = self._extract_font_info(minor_font)

    def _parse_effect_scheme(self, fmt_scheme):
        """Parse Office theme effect scheme."""
        # Parse fill style list, line style list, and effect style list
        fill_style_lst = fmt_scheme.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}fillStyleLst')
        ln_style_lst = fmt_scheme.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}lnStyleLst')
        effect_style_lst = fmt_scheme.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}effectStyleLst')

        if fill_style_lst is not None:
            self.theme_effects['fills'] = [self._extract_fill_info(fill) for fill in fill_style_lst]
        if ln_style_lst is not None:
            self.theme_effects['lines'] = [self._extract_line_info(line) for line in ln_style_lst]
        if effect_style_lst is not None:
            self.theme_effects['effects'] = [self._extract_effect_info(effect) for effect in effect_style_lst]

    def _extract_color_value(self, color_elem):
        """Extract color value from theme color element."""
        # This is a simplified implementation
        # Real implementation would parse srgbClr, sysClr, etc.
        for child in color_elem:
            if 'srgbClr' in child.tag:
                val = child.get('val')
                if val:
                    return f"#{val}"
            elif 'sysClr' in child.tag:
                val = child.get('val')
                if val:
                    return val
        return '#000000'

    def _extract_font_info(self, font_elem):
        """Extract font information from theme font element."""
        fonts = {}
        for child in font_elem:
            tag_name = child.tag.split('}')[-1]
            if tag_name in ['latin', 'ea', 'cs']:
                typeface = child.get('typeface')
                if typeface:
                    fonts[tag_name] = typeface
        return fonts

    def _extract_fill_info(self, fill_elem):
        """Extract fill information from theme fill element."""
        # Simplified implementation
        return {'type': fill_elem.tag.split('}')[-1]}

    def _extract_line_info(self, line_elem):
        """Extract line information from theme line element."""
        # Simplified implementation
        return {'type': line_elem.tag.split('}')[-1]}

    def _extract_effect_info(self, effect_elem):
        """Extract effect information from theme effect element."""
        # Simplified implementation
        return {'type': effect_elem.tag.split('}')[-1]}

    def _evaluate_themed_cell(self, cell_elem):
        """Evaluate a cell that has themed values."""
        v_value = cell_elem.get('V', '')
        f_value = cell_elem.get('F', '')
        cell_name = cell_elem.get('N', '')

        # If V="Themed", get value from theme
        if v_value.lower() == 'themed':
            # Look up in theme properties
            if cell_name in self.theme_properties:
                theme_val = self.theme_properties[cell_name]
                if theme_val != 'Themed':  # If theme has a real value
                    return theme_val
            # Fallback to inheritance
            elif f_value == 'Inh':
                return self._resolve_inherited_value(cell_elem)
            elif f_value.startswith('THEMEVAL'):
                return self._evaluate_themeval_function(f_value, cell_name)
            else:
                # Direct fallback to default
                return self._get_default_value_for_property(cell_name)

        # If F="Inh", resolve inheritance
        elif f_value == 'Inh':
            return self._resolve_inherited_value(cell_elem)

        # If F="THEMEVAL()", evaluate theme function
        elif f_value.startswith('THEMEVAL'):
            return self._evaluate_themeval_function(f_value, cell_name)

        # Default: return the V value
        return v_value

    def _evaluate_themeval_function(self, formula, cell_name):
        """Evaluate THEMEVAL() function calls."""
        if formula == 'THEMEVAL()':
            # Get value directly from theme without inheritance
            if cell_name in self.theme_properties:
                return self.theme_properties[cell_name]
            # Check theme color/font/effect schemes
            elif cell_name in self.theme_colors:
                return self.theme_colors[cell_name]
            elif cell_name in self.theme_fonts:
                return self.theme_fonts[cell_name]
        elif formula.startswith('THEMEVAL('):
            # Parse arguments and get from specific theme
            # This is more complex and would require parsing the argument
            pass

        return '0'  # Default fallback

    def _resolve_inherited_value(self, cell_elem):
        """Resolve inherited value for a cell with F='Inh'."""
        cell_name = cell_elem.get('N')

        # Try to find the value in the inheritance chain
        # This is a simplified implementation
        # Real implementation would walk the full inheritance hierarchy

        # Check if this cell exists in any parent style
        for style_data in self.styles.values():
            if cell_name in style_data.get('properties', {}):
                return style_data['properties'][cell_name]

        return '0'  # Default fallback

    def _resolve_style_inheritance(self, style_id):
        """Resolve style inheritance chain and return combined properties."""
        if not style_id or style_id not in self.styles:
            return {}

        combined_properties = {}
        current_style_id = style_id

        # Walk up the inheritance chain (typically: specific style -> root style "0")
        while current_style_id:
            if current_style_id in self.styles:
                current_style = self.styles[current_style_id]

                # Add properties from current style (child overrides parent)
                for prop_name, prop_value in current_style['properties'].items():
                    if prop_name not in combined_properties:  # Don't override if already set
                        # Evaluate themed values in the property
                        if isinstance(prop_value, str) and prop_value.lower() == 'themed':
                            combined_properties[prop_name] = self._evaluate_theme_property(prop_name)
                        else:
                            combined_properties[prop_name] = prop_value

                # Check if this style inherits from another
                if 'Style' in current_style['properties']:
                    parent_style_id = current_style['properties']['Style']
                    if parent_style_id != current_style_id:  # Avoid infinite loops
                        current_style_id = parent_style_id
                    else:
                        break
                else:
                    break
            else:
                break

        return combined_properties

    def _evaluate_theme_property(self, prop_name):
        """Evaluate a theme property by name."""
        # First check theme properties
        if prop_name in self.theme_properties:
            theme_value = self.theme_properties[prop_name]
            # If the theme value is still "Themed", we need to look deeper
            if isinstance(theme_value, str) and theme_value.lower() == 'themed':
                # This is a fallback - in a real implementation, we'd need to
                # handle more complex theme inheritance
                return self._get_default_value_for_property(prop_name)
            return theme_value

        # Check theme colors
        if prop_name in self.theme_colors:
            return self.theme_colors[prop_name]

        # Check theme fonts
        if prop_name in self.theme_fonts:
            return self.theme_fonts[prop_name]

        # Return default value for the property
        return self._get_default_value_for_property(prop_name)

    def _get_default_value_for_property(self, prop_name):
        """Get a default value for a property when theme evaluation fails."""
        defaults = {
            'LineWeight': '0.01',
            'LineColor': '0',  # Usually maps to black
            'FillForegnd': '1',  # Usually maps to white
            'FillBkgnd': '0',  # Usually maps to black
            'FillPattern': '1',
            'LinePattern': '1',
            'VerticalAlign': '1',  # Middle
            'TextBkgnd': '0',
            'LeftMargin': '0',
            'RightMargin': '0',
            'TopMargin': '0',
            'BottomMargin': '0'
        }
        return defaults.get(prop_name, '0')

    def _get_shape_style_properties(self, shape_elem):
        """Get combined style properties for a shape considering inheritance."""
        # Get style references from shape
        line_style_id = shape_elem.get('LineStyle')
        fill_style_id = shape_elem.get('FillStyle') 
        text_style_id = shape_elem.get('TextStyle')
        
        # Resolve inheritance for each style type
        line_properties = self._resolve_style_inheritance(line_style_id) if line_style_id else {}
        fill_properties = self._resolve_style_inheritance(fill_style_id) if fill_style_id else {}
        text_properties = self._resolve_style_inheritance(text_style_id) if text_style_id else {}
        
        # Also check for direct Style attribute
        direct_style_id = shape_elem.get('Style')
        if direct_style_id:
            direct_properties = self._resolve_style_inheritance(direct_style_id)
            # Direct style properties override the specific style types
            line_properties.update(direct_properties)
            fill_properties.update(direct_properties)
            text_properties.update(direct_properties)
        
        return {
            'line': line_properties,
            'fill': fill_properties,
            'text': text_properties
        }

    def _parse_shape(self, shape_elem):
        """Parse a single shape element with enhanced style support."""
        shape_id = shape_elem.get('ID')
        if not shape_id:
            return None
        
        shape_data = {
            'id': shape_id,
            'name': shape_elem.get('NameU', f'Shape{shape_id}'),
            'type': shape_elem.get('Type', 'Shape'),
            'master_id': shape_elem.get('Master'),
            'x': 0, 'y': 0, 'width': 1, 'height': 1,
            'angle': 0,
            'loc_pin_x': 0, 'loc_pin_y': 0,
            'txt_pin_x': 0, 'txt_pin_y': 0,
            'txt_width': 0, 'txt_height': 0,
            'path': '',
            'style': {
                'fill': '#ffffff',
                'stroke': '#000000',
                'stroke_width': '1'
            },
            'properties': {}
        }

        # Get combined style properties with inheritance
        style_properties = self._get_shape_style_properties(shape_elem)
        
        # Parse all cells to get shape properties and override style properties
        for cell in shape_elem.findall('.//v:Cell', self.namespaces):
            prop_name = cell.get('N')
            prop_value = self._evaluate_themed_cell(cell)

            if not prop_name:
                continue

            shape_data['properties'][prop_name] = prop_value
            
            try:
                # Extract positioning properties
                if prop_name == 'PinX':
                    shape_data['x'] = float(prop_value)
                elif prop_name == 'PinY':
                    shape_data['y'] = float(prop_value)
                elif prop_name == 'Width':
                    shape_data['width'] = float(prop_value)
                elif prop_name == 'Height':
                    shape_data['height'] = float(prop_value)
                elif prop_name == 'LocPinX':
                    shape_data['loc_pin_x'] = float(prop_value)
                elif prop_name == 'LocPinY':
                    shape_data['loc_pin_y'] = float(prop_value)
                elif prop_name == 'Angle':
                    shape_data['angle'] = float(prop_value)
                elif prop_name == 'TxtPinX':
                    shape_data['txt_pin_x'] = float(prop_value)
                elif prop_name == 'TxtPinY':
                    shape_data['txt_pin_y'] = float(prop_value)
                elif prop_name == 'TxtWidth':
                    shape_data['txt_width'] = float(prop_value)
                elif prop_name == 'TxtHeight':
                    shape_data['txt_height'] = float(prop_value)
            except (ValueError, TypeError):
                pass

        # Apply style properties to shape style
        self._apply_style_properties_to_shape(shape_data, style_properties)
        
        # Parse geometry if present
        geometry_path = self._parse_geometry_sections(shape_elem, shape_data['width'], shape_data['height'])
        if geometry_path:
            shape_data['path'] = geometry_path
        elif shape_data['master_id'] and shape_data['master_id'] in self.masters:
            # Use master geometry scaled to shape size
            master = self.masters[shape_data['master_id']]
            if master['path']:
                # Scale master path to shape dimensions
                shape_data['path'] = self._scale_path(master['path'], 
                                                    shape_data['width'] / master['width'],
                                                    shape_data['height'] / master['height'])

        # Parse rich text content with formatting
        shape_data['text_runs'] = self._parse_text_runs(shape_elem)

        # Parse text block properties
        shape_data['text_block'] = self._parse_text_block_properties(shape_elem)

        # Parse shape effects (shadows, bevels, etc.)
        shape_data['effects'] = self._parse_shape_effects(shape_elem)

        return shape_data

    def _parse_text_runs(self, shape_elem):
        """Parse text runs from a shape element according to VSDX specification."""
        text_runs = []

        # Find Text element
        text_elem = shape_elem.find('.//v:Text', self.namespaces)
        if text_elem is None:
            return text_runs

        print(f"  - Processing text for shape: {shape_elem.get('ID')}")

        # Parse text runs from the Text element
        current_run = {
            'text': '',
            'char_props': {},
            'para_props': {},
            'tabs_props': {},
            'field': None
        }

        # Process all child elements and text
        for child in text_elem:
            tag_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag

            if tag_name == 'cp':  # Character properties
                if current_run['text']:  # Save previous run if it has text
                    text_runs.append(current_run.copy())
                    current_run['text'] = ''

                # Parse character properties
                current_run['char_props'] = self._parse_char_properties(child, shape_elem)

            elif tag_name == 'pp':  # Paragraph properties
                if current_run['text']:  # Save previous run if it has text
                    text_runs.append(current_run.copy())
                    current_run['text'] = ''

                # Parse paragraph properties
                current_run['para_props'] = self._parse_para_properties(child, shape_elem)

            elif tag_name == 'tp':  # Tabs properties
                if current_run['text']:  # Save previous run if it has text
                    text_runs.append(current_run.copy())
                    current_run['text'] = ''

                # Parse tabs properties
                current_run['tabs_props'] = self._parse_tabs_properties(child, shape_elem)

            elif tag_name == 'fld':  # Text field
                if current_run['text']:  # Save previous run if it has text
                    text_runs.append(current_run.copy())
                    current_run['text'] = ''

                # Parse field
                current_run['field'] = self._parse_text_field(child, shape_elem)

            # Handle text content
            if child.text:
                current_run['text'] += child.text
            if child.tail:
                current_run['text'] += child.tail

        # Handle text directly in Text element
        if text_elem.text:
            current_run['text'] += text_elem.text

        # Add final run if it has text
        if current_run['text'].strip():
            text_runs.append(current_run)

        if text_runs:
            print(f"    - Found {len(text_runs)} text runs")

        return text_runs

    def _parse_char_properties(self, cp_elem, shape_elem):
        """Parse character properties from cp element."""
        props = {}
        ix = cp_elem.get('IX')  # Index of character properties row

        if ix:
            # Find character section and get the specified row
            char_section = shape_elem.find('.//v:Section[@N="Character"]', self.namespaces)
            if char_section is not None:
                # Find the row with matching IX
                for row in char_section.findall('v:Row', self.namespaces):
                    if row.get('IX') == ix:
                        # Parse all cells in this row
                        for cell in row.findall('v:Cell', self.namespaces):
                            cell_name = cell.get('N')
                            cell_value = self._evaluate_themed_cell(cell)
                            props[cell_name] = cell_value
                        break

        return props

    def _parse_para_properties(self, pp_elem, shape_elem):
        """Parse paragraph properties from pp element."""
        props = {}
        ix = pp_elem.get('IX')  # Index of paragraph properties row

        if ix:
            # Find paragraph section and get the specified row
            para_section = shape_elem.find('.//v:Section[@N="Paragraph"]', self.namespaces)
            if para_section is not None:
                # Find the row with matching IX
                for row in para_section.findall('v:Row', self.namespaces):
                    if row.get('IX') == ix:
                        # Parse all cells in this row
                        for cell in row.findall('v:Cell', self.namespaces):
                            cell_name = cell.get('N')
                            cell_value = self._evaluate_themed_cell(cell)
                            props[cell_name] = cell_value
                        break

        return props

    def _parse_tabs_properties(self, tp_elem, shape_elem):
        """Parse tabs properties from tp element."""
        props = {}
        ix = tp_elem.get('IX')  # Index of tabs properties row

        if ix:
            # Find tabs section and get the specified row
            tabs_section = shape_elem.find('.//v:Section[@N="Tabs"]', self.namespaces)
            if tabs_section is not None:
                # Find the row with matching IX
                for row in tabs_section.findall('v:Row', self.namespaces):
                    if row.get('IX') == ix:
                        # Parse all cells in this row
                        for cell in row.findall('v:Cell', self.namespaces):
                            cell_name = cell.get('N')
                            cell_value = self._evaluate_themed_cell(cell)
                            props[cell_name] = cell_value
                        break

        return props

    def _parse_text_field(self, fld_elem, shape_elem):
        """Parse text field from fld element."""
        field = {}
        ix = fld_elem.get('IX')  # Index of field row

        if ix:
            # Find field section and get the specified row
            field_section = shape_elem.find('.//v:Section[@N="Field"]', self.namespaces)
            if field_section is not None:
                # Find the row with matching IX
                for row in field_section.findall('v:Row', self.namespaces):
                    if row.get('IX') == ix:
                        # Parse all cells in this row
                        for cell in row.findall('v:Cell', self.namespaces):
                            cell_name = cell.get('N')
                            cell_value = self._evaluate_themed_cell(cell)
                            field[cell_name] = cell_value
                        break

        return field

    def _parse_text_block_properties(self, shape_elem):
        """Parse text block properties from shape element."""
        text_block_props = {
            'left_margin': 0,
            'right_margin': 0,
            'top_margin': 0,
            'bottom_margin': 0,
            'vertical_align': '1',  # Middle
            'text_bkgnd': '0',
            'text_direction': '0'  # Left to right
        }

        # Find text block cells in the shape
        text_block_cells = shape_elem.findall('.//v:Cell[@N="LeftMargin"]', self.namespaces)
        text_block_cells.extend(shape_elem.findall('.//v:Cell[@N="RightMargin"]', self.namespaces))
        text_block_cells.extend(shape_elem.findall('.//v:Cell[@N="TopMargin"]', self.namespaces))
        text_block_cells.extend(shape_elem.findall('.//v:Cell[@N="BottomMargin"]', self.namespaces))
        text_block_cells.extend(shape_elem.findall('.//v:Cell[@N="VerticalAlign"]', self.namespaces))
        text_block_cells.extend(shape_elem.findall('.//v:Cell[@N="TextBkgnd"]', self.namespaces))
        text_block_cells.extend(shape_elem.findall('.//v:Cell[@N="TextDirection"]', self.namespaces))

        for cell in text_block_cells:
            cell_name = cell.get('N')
            cell_value = self._evaluate_themed_cell(cell)

            if cell_name == 'LeftMargin':
                try:
                    text_block_props['left_margin'] = float(cell_value) * self.visio_to_svg_scale
                except (ValueError, TypeError):
                    pass
            elif cell_name == 'RightMargin':
                try:
                    text_block_props['right_margin'] = float(cell_value) * self.visio_to_svg_scale
                except (ValueError, TypeError):
                    pass
            elif cell_name == 'TopMargin':
                try:
                    text_block_props['top_margin'] = float(cell_value) * self.visio_to_svg_scale
                except (ValueError, TypeError):
                    pass
            elif cell_name == 'BottomMargin':
                try:
                    text_block_props['bottom_margin'] = float(cell_value) * self.visio_to_svg_scale
                except (ValueError, TypeError):
                    pass
            elif cell_name == 'VerticalAlign':
                text_block_props['vertical_align'] = cell_value
            elif cell_name == 'TextBkgnd':
                text_block_props['text_bkgnd'] = cell_value
            elif cell_name == 'TextDirection':
                text_block_props['text_direction'] = cell_value

        return text_block_props

    def _parse_shape_effects(self, shape_elem):
        """Parse shape effects (shadows, bevels, blur, etc.) from shape element."""
        effects = {
            'shadow': {},
            'bevel': {},
            'blur': 0,
            'glow': {},
            'reflection': {}
        }

        # Find shadow-related cells
        shadow_cells = shape_elem.findall('.//v:Cell[@N="ShdwForegnd"]', self.namespaces)
        shadow_cells.extend(shape_elem.findall('.//v:Cell[@N="ShdwPattern"]', self.namespaces))
        shadow_cells.extend(shape_elem.findall('.//v:Cell[@N="ShapeShdwOffsetX"]', self.namespaces))
        shadow_cells.extend(shape_elem.findall('.//v:Cell[@N="ShapeShdwOffsetY"]', self.namespaces))
        shadow_cells.extend(shape_elem.findall('.//v:Cell[@N="ShapeShdwType"]', self.namespaces))
        shadow_cells.extend(shape_elem.findall('.//v:Cell[@N="ShapeShdwObliqueAngle"]', self.namespaces))
        shadow_cells.extend(shape_elem.findall('.//v:Cell[@N="ShapeShdwScaleFactor"]', self.namespaces))
        shadow_cells.extend(shape_elem.findall('.//v:Cell[@N="ShapeShdwBlur"]', self.namespaces))
        shadow_cells.extend(shape_elem.findall('.//v:Cell[@N="ShapeShdwShow"]', self.namespaces))

        # Theme shadow cells
        shadow_cells.extend(shape_elem.findall('.//v:Cell[@N="msvThemeShadowColor"]', self.namespaces))
        shadow_cells.extend(shape_elem.findall('.//v:Cell[@N="msvThemeShadowDirection"]', self.namespaces))
        shadow_cells.extend(shape_elem.findall('.//v:Cell[@N="msvThemeShadowMagnification"]', self.namespaces))
        shadow_cells.extend(shape_elem.findall('.//v:Cell[@N="msvThemeShadowPattern"]', self.namespaces))
        shadow_cells.extend(shape_elem.findall('.//v:Cell[@N="msvThemeShadowStyle"]', self.namespaces))
        shadow_cells.extend(shape_elem.findall('.//v:Cell[@N="msvThemeShadowTransparency"]', self.namespaces))
        shadow_cells.extend(shape_elem.findall('.//v:Cell[@N="msvThemeShadowXOffset"]', self.namespaces))
        shadow_cells.extend(shape_elem.findall('.//v:Cell[@N="msvThemeShadowYOffset"]', self.namespaces))

        for cell in shadow_cells:
            cell_name = cell.get('N')
            cell_value = self._evaluate_themed_cell(cell)

            if cell_name == 'ShdwForegnd' or cell_name == 'msvThemeShadowColor':
                effects['shadow']['color'] = cell_value
            elif cell_name == 'ShdwPattern' or cell_name == 'msvThemeShadowPattern':
                effects['shadow']['pattern'] = cell_value
            elif cell_name == 'ShapeShdwOffsetX' or cell_name == 'msvThemeShadowXOffset':
                try:
                    effects['shadow']['offset_x'] = float(cell_value) * self.visio_to_svg_scale
                except (ValueError, TypeError):
                    effects['shadow']['offset_x'] = 4
            elif cell_name == 'ShapeShdwOffsetY' or cell_name == 'msvThemeShadowYOffset':
                try:
                    effects['shadow']['offset_y'] = float(cell_value) * self.visio_to_svg_scale
                except (ValueError, TypeError):
                    effects['shadow']['offset_y'] = 4
            elif cell_name == 'ShapeShdwType':
                effects['shadow']['type'] = cell_value
            elif cell_name == 'ShapeShdwObliqueAngle':
                effects['shadow']['angle'] = cell_value
            elif cell_name == 'ShapeShdwScaleFactor':
                effects['shadow']['scale'] = cell_value
            elif cell_name == 'ShapeShdwBlur':
                try:
                    effects['shadow']['blur'] = float(cell_value) * self.visio_to_svg_scale
                except (ValueError, TypeError):
                    effects['shadow']['blur'] = 2
            elif cell_name == 'ShapeShdwShow':
                effects['shadow']['enabled'] = cell_value == '1'
            elif cell_name == 'msvThemeShadowDirection':
                effects['shadow']['direction'] = cell_value
            elif cell_name == 'msvThemeShadowMagnification':
                effects['shadow']['magnification'] = cell_value
            elif cell_name == 'msvThemeShadowStyle':
                effects['shadow']['style'] = cell_value
            elif cell_name == 'msvThemeShadowTransparency':
                effects['shadow']['transparency'] = cell_value

        # Find bevel-related cells
        bevel_cells = shape_elem.findall('.//v:Cell[@N="BevelTopType"]', self.namespaces)
        bevel_cells.extend(shape_elem.findall('.//v:Cell[@N="BevelTopWidth"]', self.namespaces))
        bevel_cells.extend(shape_elem.findall('.//v:Cell[@N="BevelTopHeight"]', self.namespaces))
        bevel_cells.extend(shape_elem.findall('.//v:Cell[@N="BevelBottomType"]', self.namespaces))
        bevel_cells.extend(shape_elem.findall('.//v:Cell[@N="BevelBottomWidth"]', self.namespaces))
        bevel_cells.extend(shape_elem.findall('.//v:Cell[@N="BevelBottomHeight"]', self.namespaces))
        bevel_cells.extend(shape_elem.findall('.//v:Cell[@N="BevelDepthColor"]', self.namespaces))
        bevel_cells.extend(shape_elem.findall('.//v:Cell[@N="BevelDepthSize"]', self.namespaces))
        bevel_cells.extend(shape_elem.findall('.//v:Cell[@N="BevelContourColor"]', self.namespaces))
        bevel_cells.extend(shape_elem.findall('.//v:Cell[@N="BevelContourSize"]', self.namespaces))
        bevel_cells.extend(shape_elem.findall('.//v:Cell[@N="BevelLightingType"]', self.namespaces))
        bevel_cells.extend(shape_elem.findall('.//v:Cell[@N="BevelLightingAngle"]', self.namespaces))
        bevel_cells.extend(shape_elem.findall('.//v:Cell[@N="BevelMaterialType"]', self.namespaces))

        for cell in bevel_cells:
            cell_name = cell.get('N')
            cell_value = self._evaluate_themed_cell(cell)

            if cell_name == 'BevelTopType':
                effects['bevel']['top_type'] = cell_value
            elif cell_name == 'BevelTopWidth':
                try:
                    effects['bevel']['top_width'] = float(cell_value) * self.visio_to_svg_scale
                except (ValueError, TypeError):
                    effects['bevel']['top_width'] = 0
            elif cell_name == 'BevelTopHeight':
                try:
                    effects['bevel']['top_height'] = float(cell_value) * self.visio_to_svg_scale
                except (ValueError, TypeError):
                    effects['bevel']['top_height'] = 0
            elif cell_name == 'BevelBottomType':
                effects['bevel']['bottom_type'] = cell_value
            elif cell_name == 'BevelBottomWidth':
                try:
                    effects['bevel']['bottom_width'] = float(cell_value) * self.visio_to_svg_scale
                except (ValueError, TypeError):
                    effects['bevel']['bottom_width'] = 0
            elif cell_name == 'BevelBottomHeight':
                try:
                    effects['bevel']['bottom_height'] = float(cell_value) * self.visio_to_svg_scale
                except (ValueError, TypeError):
                    effects['bevel']['bottom_height'] = 0
            elif cell_name == 'BevelDepthColor':
                effects['bevel']['depth_color'] = cell_value
            elif cell_name == 'BevelDepthSize':
                try:
                    effects['bevel']['depth_size'] = float(cell_value) * self.visio_to_svg_scale
                except (ValueError, TypeError):
                    effects['bevel']['depth_size'] = 0
            elif cell_name == 'BevelContourColor':
                effects['bevel']['contour_color'] = cell_value
            elif cell_name == 'BevelContourSize':
                try:
                    effects['bevel']['contour_size'] = float(cell_value) * self.visio_to_svg_scale
                except (ValueError, TypeError):
                    effects['bevel']['contour_size'] = 0
            elif cell_name == 'BevelLightingType':
                effects['bevel']['lighting_type'] = cell_value
            elif cell_name == 'BevelLightingAngle':
                effects['bevel']['lighting_angle'] = cell_value
            elif cell_name == 'BevelMaterialType':
                effects['bevel']['material_type'] = cell_value

        # Find blur effect
        blur_cell = shape_elem.find('.//v:Cell[@N="Blur"]', self.namespaces)
        if blur_cell is not None:
            blur_value = self._evaluate_themed_cell(blur_cell)
            try:
                effects['blur'] = float(blur_value) * self.visio_to_svg_scale
            except (ValueError, TypeError):
                effects['blur'] = 0

        # Debug: Print effects if found
        if any(effects.values()):
            print(f"  - Found effects for shape: shadow={bool(effects['shadow'])}, bevel={bool(effects['bevel'])}, blur={effects['blur']}")

        return effects

    def _apply_style_properties_to_shape(self, shape_data, style_properties):
        """Apply resolved style properties to shape's SVG style."""
        # Line properties
        line_props = style_properties.get('line', {})
        if 'LineColor' in line_props:
            line_color = line_props['LineColor']
            # Handle both direct color values and color index references
            if line_color in self.colors:
                shape_data['style']['stroke'] = self.colors[line_color]
            elif line_color.startswith('#'):
                shape_data['style']['stroke'] = line_color
            elif line_color in self.theme_colors:
                shape_data['style']['stroke'] = self.theme_colors[line_color]

        if 'LineWeight' in line_props:
            weight = max(0.5, float(line_props['LineWeight']) * self.visio_to_svg_scale)
            shape_data['style']['stroke_width'] = str(weight)

        if 'LinePattern' in line_props:
            # Convert Visio line patterns to SVG stroke-dasharray
            pattern = line_props['LinePattern']
            if pattern == '2':  # Dashed
                shape_data['style']['stroke_dasharray'] = '5,3'
            elif pattern == '3':  # Dotted
                shape_data['style']['stroke_dasharray'] = '1,2'

        # Fill properties
        fill_props = style_properties.get('fill', {})
        if 'FillForegnd' in fill_props:
            fill_color = fill_props['FillForegnd']
            # Handle both direct color values and color index references
            if fill_color in self.colors:
                shape_data['style']['fill'] = self.colors[fill_color]
            elif fill_color.startswith('#'):
                shape_data['style']['fill'] = fill_color
            elif fill_color in self.theme_colors:
                shape_data['style']['fill'] = self.theme_colors[fill_color]

        if 'FillPattern' in fill_props and fill_props['FillPattern'] == '0':
            shape_data['style']['fill'] = 'none'

        # Text properties
        text_props = style_properties.get('text', {})
        if 'VerticalAlign' in text_props:
            valign = text_props['VerticalAlign']
            if valign == '0':
                shape_data['style']['text_anchor'] = 'start'
            elif valign == '1':
                shape_data['style']['text_anchor'] = 'middle'
            elif valign == '2':
                shape_data['style']['text_anchor'] = 'end'

    def _generate_css_class(self, style_dict):
        """Generate a CSS class for the given style properties."""
        # Create a unique key for this style combination
        style_key = str(sorted(style_dict.items()))
        
        if style_key in self.css_classes:
            return self.css_classes[style_key]
        
        class_name = f"st{self.class_counter}"
        self.class_counter += 1
        self.css_classes[style_key] = class_name
        
        return class_name

    def _generate_css_styles(self):
        """Generate CSS style definitions."""
        css_lines = []
        
        for style_key, class_name in self.css_classes.items():
            # Parse the style key back to dictionary
            style_dict = dict(eval(style_key))
            
            css_props = []
            for prop, value in style_dict.items():
                if prop == 'stroke':
                    css_props.append(f"stroke:{value}")
                elif prop == 'fill':
                    css_props.append(f"fill:{value}")
                elif prop == 'stroke_width':
                    css_props.append(f"stroke-width:{value}")
                elif prop == 'stroke_dasharray':
                    css_props.append(f"stroke-dasharray:{value}")
                elif prop == 'text_anchor':
                    css_props.append(f"text-anchor:{value}")
                elif prop == 'dominant_baseline':
                    css_props.append(f"dominant-baseline:{value}")
            
            if css_props:
                css_lines.append(f".{class_name} {{ {'; '.join(css_props)}; }}")
        
        return '\n'.join(css_lines)

    def _parse_masters(self, zf):
        """Parse master shape definitions."""
        print("Parsing master shapes...")
        
        # Parse master relationships
        rel_ns = {'rel': 'http://schemas.openxmlformats.org/package/2006/relationships'}
        master_rel_map = {}
        
        rels_tree = self._get_xml_tree(zf, 'visio/masters/_rels/masters.xml.rels')
        if rels_tree:
            for rel in rels_tree.findall('rel:Relationship', rel_ns):
                master_rel_map[rel.get('Id')] = rel.get('Target')

        masters_tree = self._get_xml_tree(zf, 'visio/masters/masters.xml')
        if not masters_tree:
            return

        for master in masters_tree.findall('v:Master', self.namespaces):
            master_id = master.get('ID')
            master_name = master.get('NameU', f'Master{master_id}')
            
            rel_elem = master.find('v:Rel', self.namespaces)
            rel_id = rel_elem.get(f'{{{self.namespaces["r"]}}}id') if rel_elem is not None else None
            
            if rel_id and rel_id in master_rel_map:
                master_file_path = f"visio/masters/{master_rel_map[rel_id]}"
                master_tree = self._get_xml_tree(zf, master_file_path)
                if master_tree:
                    master_data = self._parse_master_shape(master_tree, master_id, master_name)
                    self.masters[master_id] = master_data
                    print(f"  - Parsed Master {master_id}: {master_name}")

    def _parse_master_shape(self, master_tree, master_id, master_name):
        """Parse geometry and properties from a master shape."""
        master_data = {
            'id': master_id,
            'name': master_name,
            'path': '',
            'width': 1.0,
            'height': 1.0,
            'properties': {}
        }

        # Get dimensions
        width_cell = master_tree.find('.//v:Cell[@N="Width"]', self.namespaces)
        height_cell = master_tree.find('.//v:Cell[@N="Height"]', self.namespaces)
        
        if width_cell is not None:
            try:
                width_value = self._evaluate_themed_cell(width_cell)
                master_data['width'] = float(width_value)
            except:
                master_data['width'] = 1.0
        if height_cell is not None:
            try:
                height_value = self._evaluate_themed_cell(height_cell)
                master_data['height'] = float(height_value)
            except:
                master_data['height'] = 1.0

        # Parse geometry sections
        path_data = self._parse_geometry_sections(master_tree, master_data['width'], master_data['height'])
        master_data['path'] = path_data

        return master_data

    def _parse_geometry_sections(self, tree, shape_width=1.0, shape_height=1.0):
        """Parse geometry sections and convert to SVG path data."""
        path_data = ""
        
        for geom_section in tree.findall('.//v:Section[@N="Geometry"]', self.namespaces):
            section_path = ""
            
            # Check if this geometry should be drawn
            no_show_cell = geom_section.find('v:Cell[@N="NoShow"]', self.namespaces)
            if no_show_cell is not None and no_show_cell.get('V', '0') == '1':
                continue
            
            rows = geom_section.findall('v:Row', self.namespaces)
            if not rows:
                continue
                
            for row in rows:
                row_type = row.get('T')
                
                x_cell = row.find('v:Cell[@N="X"]', self.namespaces)
                y_cell = row.find('v:Cell[@N="Y"]', self.namespaces)
                
                if x_cell is not None and y_cell is not None:
                    try:
                        x = float(x_cell.get('V', '0'))
                        y = float(y_cell.get('V', '0'))
                        
                        # Convert to SVG coordinates (scale and invert Y)
                        svg_x = x * self.visio_to_svg_scale
                        svg_y = (shape_height - y) * self.visio_to_svg_scale
                        
                        if row_type == 'MoveTo':
                            section_path += f"M {svg_x:.2f} {svg_y:.2f} "
                        elif row_type == 'LineTo':
                            section_path += f"L {svg_x:.2f} {svg_y:.2f} "
                        elif row_type == 'ArcTo':
                            # Simple arc handling
                            section_path += f"L {svg_x:.2f} {svg_y:.2f} "
                        elif row_type == 'EllipticalArcTo':
                            section_path += f"L {svg_x:.2f} {svg_y:.2f} "
                        elif row_type == 'Ellipse':
                            # Handle ellipse geometry
                            cx = svg_x
                            cy = svg_y
                            rx = shape_width * self.visio_to_svg_scale / 2
                            ry = shape_height * self.visio_to_svg_scale / 2
                            section_path += f"M {cx-rx:.2f} {cy:.2f} A {rx:.2f} {ry:.2f} 0 1 1 {cx+rx:.2f} {cy:.2f} A {rx:.2f} {ry:.2f} 0 1 1 {cx-rx:.2f} {cy:.2f} "
                    except (ValueError, TypeError):
                        continue
            
            # Check if path should be closed
            no_fill_cell = geom_section.find('v:Cell[@N="NoFill"]', self.namespaces)
            if section_path and (no_fill_cell is None or no_fill_cell.get('V', '0') == '0'):
                section_path += "Z "
            
            path_data += section_path
        
        return path_data.strip()

    def _parse_page_shapes(self):
        """Parse shapes from the page XML."""
        print("Parsing page shapes...")
        
        # Find page XML
        page_xml_path = 'visio/pages/page1.xml'
        try:
            page_rels_tree = self._get_xml_tree(self.zf, 'visio/pages/_rels/pages.xml.rels')
            if page_rels_tree is not None:
                rel_ns = {'rel': 'http://schemas.openxmlformats.org/package/2006/relationships'}
                first_rel = page_rels_tree.find('.//rel:Relationship', rel_ns)
                if first_rel is not None:
                    target = first_rel.get('Target')
                    if target:
                        page_xml_path = f'visio/pages/{target}'
        except:
            pass

        page_tree = self._get_xml_tree(self.zf, page_xml_path)
        if page_tree is None:
            print(f"Error: Could not parse page XML at '{page_xml_path}'")
            return

        # Find all shapes
        shapes = page_tree.findall('.//v:Shape', self.namespaces)
        print(f"Found {len(shapes)} shapes in page")
        
        for shape_elem in shapes:
            shape_data = self._parse_shape(shape_elem)
            if shape_data:
                self.shapes[shape_data['id']] = shape_data
                self.page_shapes.append(shape_data['id'])

    def _scale_path(self, path, scale_x, scale_y):
        """Scale SVG path coordinates."""
        if not path:
            return path
        
        import re
        
        def scale_coords(match):
            coords = match.group(1).split()
            scaled_coords = []
            for i in range(0, len(coords), 2):
                if i + 1 < len(coords):
                    try:
                        x = float(coords[i]) * scale_x
                        y = float(coords[i + 1]) * scale_y
                        scaled_coords.extend([f"{x:.2f}", f"{y:.2f}"])
                    except:
                        scaled_coords.extend([coords[i], coords[i + 1]])
                else:
                    scaled_coords.append(coords[i])
            return match.group(0)[0] + " " + " ".join(scaled_coords) + " "
        
        # Scale coordinate pairs after M, L, etc.
        scaled_path = re.sub(r'([ML])\s+([\d\.\-\s]+)', scale_coords, path)
        return scaled_path

    def _generate_svg_content(self):
        """Generate SVG content from parsed shapes."""
        svg_elements = []
        
        for shape_id in self.page_shapes:
            if shape_id not in self.shapes:
                continue
                
            shape = self.shapes[shape_id]
            svg_element = self._shape_to_svg(shape)
            if svg_element:
                svg_elements.append(svg_element)
        
        return '\n'.join(svg_elements)

    def _shape_to_svg(self, shape):
        """Convert a shape to SVG element with CSS classes."""
        if not shape['path'] and not shape.get('text_runs') and shape['width'] <= 0:
            return None
            
        elements = []
        
        # Calculate shape position in SVG coordinate system
        svg_x = shape['x'] * self.visio_to_svg_scale
        svg_y = (self.page_height / self.visio_to_svg_scale - shape['y']) * self.visio_to_svg_scale
        
        # Create transform for the shape
        transform_parts = []
        if svg_x != 0 or svg_y != 0:
            transform_parts.append(f"translate({svg_x:.2f}, {svg_y:.2f})")
        
        if shape['angle'] != 0:
            angle_deg = math.degrees(shape['angle']) if abs(shape['angle']) < 6.28 else shape['angle']
            transform_parts.append(f"rotate({angle_deg:.2f})")
        
        transform_attr = f' transform="{" ".join(transform_parts)}"' if transform_parts else ''
        
        # Generate CSS class for this shape's style
        css_class = self._generate_css_class(shape['style'])
        
        # Create group for the shape
        elements.append(f'<g id="shape-{shape["id"]}" class="{css_class}"{transform_attr}>')
        
        # Add path if available
        if shape['path']:
            elements.append(f'  <path d="{shape["path"]}"/>')
        
        # Add rectangle if no path but has dimensions
        elif shape['width'] > 0 and shape['height'] > 0:
            width_px = shape['width'] * self.visio_to_svg_scale
            height_px = shape['height'] * self.visio_to_svg_scale
            
            # Position rectangle relative to shape's pin point
            rect_x = -shape['loc_pin_x'] * self.visio_to_svg_scale
            rect_y = -(shape['height'] - shape['loc_pin_y']) * self.visio_to_svg_scale
            
            elements.append(f'  <rect x="{rect_x:.2f}" y="{rect_y:.2f}" '
                          f'width="{width_px:.2f}" height="{height_px:.2f}"/>')
        
        # Add text if available
        if shape.get('text_runs') and shape['text_runs']:
            text_svg = self._convert_text_runs_to_svg(shape)
            if text_svg:
                elements.append(text_svg)
        
        elements.append('</g>')

        # Apply shape effects (shadows, bevels, blur) if any
        elements = self._apply_effects_to_shape(shape, elements)

        return '\n'.join(elements)

    def _convert_text_runs_to_svg(self, shape):
        """Convert text runs to SVG text elements with proper formatting."""
        if not shape.get('text_runs'):
            return None

        elements = []
        text_block = shape.get('text_block', {})

        # Calculate text block position (using text block coordinate system)
        # Default position if no specific text positioning is set
        text_x = (shape['txt_pin_x'] - shape['x']) * self.visio_to_svg_scale if shape['txt_pin_x'] != 0 else 0
        text_y = (shape['y'] - shape['txt_pin_y']) * self.visio_to_svg_scale if shape['txt_pin_y'] != 0 else 0

        # Apply text block margins
        text_x += text_block.get('left_margin', 0)

        # Create a group for all text elements
        elements.append(f'  <g class="text-block">')

        current_y = text_y + text_block.get('top_margin', 0)
        line_height = 12  # Default line height in pixels

        for run in shape['text_runs']:
            if not run['text'].strip():
                continue

            # Generate CSS class for this text run's character formatting
            text_style = self._convert_char_props_to_css(run['char_props'])
            text_css_class = self._generate_css_class(text_style)
            
            # Clean up text content
            clean_text = run['text'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

            # Handle paragraph properties
            para_props = run['para_props']
            if para_props:
                # Handle horizontal alignment
                text_anchor = 'start'
                if 'HorzAlign' in para_props:
                    align_val = para_props['HorzAlign']
                    if align_val == '1':  # Center
                        text_anchor = 'middle'
                    elif align_val == '2':  # Right
                        text_anchor = 'end'

                # Handle indentation
                indent_left = 0
                if 'IndLeft' in para_props:
                    try:
                        indent_left = float(para_props['IndLeft']) * self.visio_to_svg_scale
                    except (ValueError, TypeError):
                        pass

                adjusted_x = text_x + indent_left
            else:
                adjusted_x = text_x
                text_anchor = 'start'

            # Handle text direction (vertical text)
            text_direction = text_block.get('text_direction', '0')
            if text_direction == '1':  # Vertical text
                # For vertical text, we'll rotate the text element
                transform = f' rotate(90 {adjusted_x:.2f} {current_y:.2f})'
            else:
                transform = ''

            # Create text element
            elements.append(f'    <text x="{adjusted_x:.2f}" y="{current_y:.2f}" '
                          f'text-anchor="{text_anchor}" class="{text_css_class}"{transform}>'
                          f'{clean_text}</text>')
        
            # Handle line breaks (simple implementation)
            if '\n' in run['text'] or '\r' in run['text']:
                current_y += line_height

        elements.append('  </g>')
        
        return '\n'.join(elements)

    def _convert_char_props_to_css(self, char_props):
        """Convert Visio character properties to CSS style dictionary."""
        css_style = {
            'font-family': 'Arial, sans-serif',
            'font-size': '10px',
            'fill': 'black',
            'font-weight': 'normal',
            'font-style': 'normal',
            'text-decoration': 'none'
        }

        if not char_props:
            return css_style

        # Font family
        if 'Font' in char_props:
            font_id = char_props['Font']
            # Try to map font ID to font name (simplified)
            font_names = {
                '0': 'Arial',
                '1': 'Times New Roman',
                '2': 'Courier New',
                '3': 'Symbol',
                '4': 'Wingdings'
            }
            if font_id in font_names:
                css_style['font-family'] = font_names[font_id]

        # Font size
        if 'Size' in char_props:
            try:
                size_points = float(char_props['Size'])
                css_style['font-size'] = f'{size_points:.1f}px'
            except (ValueError, TypeError):
                pass

        # Font color
        if 'Color' in char_props:
            color_id = char_props['Color']
            if color_id in self.colors:
                css_style['fill'] = self.colors[color_id]
            elif color_id.startswith('#'):
                css_style['fill'] = color_id
            elif color_id in self.theme_colors:
                css_style['fill'] = self.theme_colors[color_id]

        # Font weight
        if 'Style' in char_props:
            style_val = char_props['Style']
            if style_val and int(float(style_val)) & 1:  # Bold bit
                css_style['font-weight'] = 'bold'
            if style_val and int(float(style_val)) & 2:  # Italic bit
                css_style['font-style'] = 'italic'
            if style_val and int(float(style_val)) & 4:  # Underline bit
                css_style['text-decoration'] = 'underline'

        # Individual style properties
        if 'DblUnderline' in char_props and char_props['DblUnderline'] == '1':
            css_style['text-decoration'] = 'underline'

        if 'Overline' in char_props and char_props['Overline'] == '1':
            css_style['text-decoration'] = 'overline'

        if 'Strikethru' in char_props and char_props['Strikethru'] == '1':
            css_style['text-decoration'] = 'line-through'

        return css_style

    def _generate_svg_filters(self):
        """Generate SVG filter definitions for shape effects."""
        filters = []

        # Generate filters for each shape that has effects
        for shape_id in self.page_shapes:
            if shape_id not in self.shapes:
                continue

            shape = self.shapes[shape_id]
            effects = shape.get('effects', {})

            # Check if shape has any effects that need SVG filters
            has_shadow = effects.get('shadow', {}).get('enabled', False) and effects['shadow']
            has_bevel = any(effects.get('bevel', {}).values())
            has_blur = effects.get('blur', 0) > 0

            if has_shadow or has_bevel or has_blur:
                filter_id = f"filter-{shape_id}"
                filter_def = self._create_svg_filter(filter_id, effects)
                if filter_def:
                    filters.append(filter_def)
                    # Store filter reference for use in shape rendering
                    shape['filter_id'] = filter_id

        return '\n'.join(filters)

    def _create_svg_filter(self, filter_id, effects):
        """Create SVG filter definition for shape effects."""
        filter_elements = []

        # Add blur effect
        if effects.get('blur', 0) > 0:
            blur_radius = max(0.5, effects['blur'])
            filter_elements.append(f'<feGaussianBlur stdDeviation="{blur_radius}"/>')

        # Add shadow effect
        shadow = effects.get('shadow', {})
        if shadow.get('enabled', False) and shadow:
            offset_x = shadow.get('offset_x', 4)
            offset_y = shadow.get('offset_y', 4)
            blur_radius = shadow.get('blur', 2)

            # Shadow color - default to black with some transparency
            shadow_color = shadow.get('color', '0')
            if shadow_color in self.colors:
                shadow_color = self.colors[shadow_color]
            elif shadow_color.startswith('#'):
                pass  # Already a hex color
            else:
                shadow_color = '#000000'

            # Add opacity from transparency if available
            opacity = 0.3  # Default shadow opacity
            if 'transparency' in shadow:
                try:
                    # Visio transparency is usually 0-100, convert to 0-1
                    opacity = 1.0 - (float(shadow['transparency']) / 100.0)
                    opacity = max(0.1, min(1.0, opacity))
                except (ValueError, TypeError):
                    pass

            filter_elements.append(f'<feDropShadow dx="{offset_x}" dy="{offset_y}" stdDeviation="{blur_radius}" flood-color="{shadow_color}" flood-opacity="{opacity}"/>')

        # Add bevel effect (simplified - using multiple offset blurs to simulate 3D effect)
        bevel = effects.get('bevel', {})
        if any(bevel.values()):
            # Create a simple bevel effect using multiple gaussian blurs and composites
            bevel_height = bevel.get('top_height', 0) + bevel.get('bottom_height', 0)
            if bevel_height > 0:
                # Light highlight (top-left)
                filter_elements.append('<feMorphology operator="dilate" radius="1"/>')
                filter_elements.append('<feComposite in="SourceGraphic" operator="over"/>')
                # Dark shadow (bottom-right)
                filter_elements.append('<feMorphology operator="erode" radius="1"/>')
                filter_elements.append('<feComposite in="SourceGraphic" operator="over"/>')

        # If no effects, return None
        if not filter_elements:
            return None

        # Create the complete filter definition
        filter_content = '\n'.join(f'      {elem}' for elem in filter_elements)

        return f'''    <filter id="{filter_id}" x="-50%" y="-50%" width="200%" height="200%">
{filter_content}
    </filter>'''

    def _apply_effects_to_shape(self, shape, elements):
        """Apply effects to shape elements by adding filter references."""
        effects = shape.get('effects', {})
        filter_id = shape.get('filter_id')

        if filter_id and (effects.get('shadow', {}).get('enabled') or
                         any(effects.get('bevel', {}).values()) or
                         effects.get('blur', 0) > 0):
            # Find the main shape element (path or rect) and add filter
            for i, element in enumerate(elements):
                if '<path' in element or '<rect' in element:
                    # Add filter attribute to the element
                    if 'filter=' not in element:
                        # Insert filter attribute before the closing >
                        elements[i] = element.replace('>', f' filter="url(#{filter_id})">')
                    break

        return elements

    def convert(self):
        """Main conversion method with enhanced style support."""
        print(f"Starting enhanced conversion of '{self.vsdx_file_path}'...")
        
        try:
            self.zf = zipfile.ZipFile(self.vsdx_file_path, 'r')
        except Exception as e:
            print(f"Error opening VSDX file: {e}")
            return None

        try:
            # Parse document components in correct order
            self._parse_colors(self.zf)
            self._parse_themed_values(self.zf)  # Parse themes before styles to resolve themed values
            self._parse_styles(self.zf)
            self._parse_page_styles(self.zf)
            self._parse_masters(self.zf)
            self._parse_page_shapes()
            
            # Generate SVG content
            shapes_svg = self._generate_svg_content()
            css_styles = self._generate_css_styles()
            svg_filters = self._generate_svg_filters()
            
            # Create complete SVG document
            svg_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" 
     xmlns:xlink="http://www.w3.org/1999/xlink"
     width="{self.page_width:.0f}" 
     height="{self.page_height:.0f}" 
     viewBox="0 0 {self.page_width:.0f} {self.page_height:.0f}">
  <title>Converted from VSDX</title>
  <desc>Generated by Enhanced VSDX to SVG Converter v3</desc>
  
  <!-- Define styles -->
    <style type="text/css">
    <![CDATA[
{css_styles}
    
    /* Default Visio shape styles */
      .visio-shape {{ 
        fill: white; 
        stroke: black; 
        stroke-width: 1; 
      stroke-linecap: round;
      stroke-linejoin: round;
      }}
      .visio-text {{
        font-family: Arial, sans-serif;
        font-size: 10px;
        text-anchor: middle;
        dominant-baseline: middle;
      fill: black;
      }}
    .text-block {{
      /* Text block container styles */
    }}
    ]]>
    </style>

  <!-- Filters for shape effects -->
  <defs>
{svg_filters}
  </defs>
  
  <!-- Shapes -->
{shapes_svg}
  
</svg>'''
            
            # Count shapes with effects
            shapes_with_effects = sum(1 for shape_id in self.page_shapes
                                    if shape_id in self.shapes and
                                    self.shapes[shape_id].get('effects') and
                                    any(self.shapes[shape_id]['effects'].values()))

            print(f"Successfully converted {len(self.shapes)} shapes with {len(self.css_classes)} style classes")
            print(f"Applied effects to {shapes_with_effects} shapes (shadows, bevels, blur)")
            return svg_content

        except Exception as e:
            print(f"Error during conversion: {e}")
            import traceback
            traceback.print_exc()
            return None

        finally:
            if self.zf:
                self.zf.close()


# Usage example
if __name__ == '__main__':
    input_vsdx_file = "diagram.vsdx"  # Replace with your VSDX file path
    output_svg_file = "output.svg"    # Replace with desired output path

    converter = VsdxToSvgConverter(input_vsdx_file)
    svg_data = converter.convert()

    if svg_data:
        with open(output_svg_file, "w", encoding="utf-8") as f:
            f.write(svg_data)
        print(f"\nConversion successful! Enhanced SVG with theme support saved to '{output_svg_file}'")
        print(f"Processed {len(converter.shapes)} shapes with {len(converter.styles)} styles")
        print(f"Found {len(converter.theme_properties)} theme properties")
    else:
        print("\nConversion failed.")