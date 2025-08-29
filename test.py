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
                
                # Parse ALL style properties
                for cell_elem in style_elem.findall('v:Cell', self.namespaces):
                    cell_name = cell_elem.get('N')
                    cell_value = cell_elem.get('V', '0')
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
            cell_value = cell_elem.get('V', '0')
            properties[cell_name] = cell_value
        return properties

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
            'text': '',
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
            prop_value = cell.get('V', '0')
            
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

        # Parse text content - check multiple possible locations
        text_content = ""
        
        # Check v:Text element
        text_elem = shape_elem.find('.//v:Text', self.namespaces)
        if text_elem is not None:
            if text_elem.text:
                text_content = text_elem.text.strip()
            # Also check for text in child elements
            for child in text_elem:
                if child.text:
                    text_content += child.text.strip() + " "
        
        # If no text found, check text in property values
        if not text_content:
            for prop_name, prop_value in shape_data['properties'].items():
                if 'text' in prop_name.lower() and prop_value and prop_value not in ['0', '1']:
                    text_content = prop_value
                    break
        
        shape_data['text'] = text_content.strip()

        return shape_data

    def _apply_style_properties_to_shape(self, shape_data, style_properties):
        """Apply resolved style properties to shape's SVG style."""
        # Line properties
        line_props = style_properties.get('line', {})
        if 'LineColor' in line_props and line_props['LineColor'] in self.colors:
            shape_data['style']['stroke'] = self.colors[line_props['LineColor']]
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
        if 'FillForegnd' in fill_props and fill_props['FillForegnd'] in self.colors:
            shape_data['style']['fill'] = self.colors[fill_props['FillForegnd']]
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
                master_data['width'] = float(width_cell.get('V', '1'))
            except:
                master_data['width'] = 1.0
        if height_cell is not None:
            try:
                master_data['height'] = float(height_cell.get('V', '1'))
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
        if not shape['path'] and not shape['text'] and shape['width'] <= 0:
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
        if shape['text']:
            # Calculate text position
            text_x = (shape['txt_pin_x'] - shape['x']) * self.visio_to_svg_scale if shape['txt_pin_x'] != 0 else 0
            text_y = (shape['y'] - shape['txt_pin_y']) * self.visio_to_svg_scale if shape['txt_pin_y'] != 0 else 0
            
            # Clean up text content
            clean_text = shape['text'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
            text_style = dict(shape['style'])
            text_css_class = self._generate_css_class(text_style)
            
            elements.append(f'  <text x="{text_x:.2f}" y="{text_y:.2f}" '
                          f'class="{text_css_class}">'
                          f'{clean_text}</text>')
        
        elements.append('</g>')
        
        return '\n'.join(elements)

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
            self._parse_styles(self.zf)
            self._parse_page_styles(self.zf)
            self._parse_masters(self.zf)
            self._parse_page_shapes()
            
            # Generate SVG content
            shapes_svg = self._generate_svg_content()
            css_styles = self._generate_css_styles()
            
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
    ]]>
  </style>
  
  <!-- Shapes -->
{shapes_svg}
  
</svg>'''
            
            print(f"Successfully converted {len(self.shapes)} shapes with {len(self.css_classes)} style classes")
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
        print(f"\nConversion successful! SVG saved to '{output_svg_file}'")
    else:
        print("\nConversion failed.")