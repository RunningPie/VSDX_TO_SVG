import zipfile
import xml.etree.ElementTree as ET
import argparse
import math
import html
import sys
import os
import re

class VSDXToSVGConverter:
    """
    Enhanced class to convert VSDX (Visio) files to SVG format with improved accuracy.
    """

    def __init__(self):
        """Initializes the converter with necessary instance variables."""
        self.page_width = 612  # Default 8.5" at 72 DPI
        self.page_height = 792  # Default 11" at 72 DPI
        self.masters = {}
        self.shapes = {}
        self.connectors = {}
        self.master_rel_map = {}
        self.namespaces = {
            'v': 'http://schemas.microsoft.com/office/visio/2012/main',
            'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
        }
        # Visio uses inches internally, convert to pixels
        self.DPI = 72
        self.INCHES_TO_PIXELS = self.DPI

    def _get_xml_tree(self, zip_file, xml_path):
        """Reads and parses an XML file from the ZIP archive."""
        try:
            with zip_file.open(xml_path) as xml_data:
                return ET.parse(xml_data)
        except (KeyError, ET.ParseError) as e:
            print(f"Warning: Could not read or parse {xml_path}. Error: {e}", file=sys.stderr)
            return None

    def _evaluate_formula(self, formula, context=None):
        """Enhanced formula evaluation with better support for Visio formulas."""
        if not formula:
            return 0.0
            
        # Default context values
        if context is None:
            context = {}
            
        # Handle common Visio functions and references
        formula = formula.strip()
        
        # Replace common Visio references
        replacements = {
            'Width': str(context.get('width', 1)),
            'Height': str(context.get('height', 1)),
            'PinX': str(context.get('pin_x', 0)),
            'PinY': str(context.get('pin_y', 0)),
            'LocPinX': str(context.get('loc_pin_x', 0)),
            'LocPinY': str(context.get('loc_pin_y', 0)),
        }
        
        for key, value in replacements.items():
            formula = re.sub(r'\b' + key + r'\b', value, formula)
        
        # Handle simple arithmetic operations
        try:
            # Remove any remaining non-numeric characters except operators
            formula = re.sub(r'[^0-9+\-*/.() ]', '', formula)
            if formula:
                return float(eval(formula))
        except:
            pass
            
        return 0.0

    def _parse_page_dimensions(self, zip_file):
        """Enhanced page dimension parsing with better fallback handling."""
        try:
            # Try to get from the first page file
            page_rels_tree = self._get_xml_tree(zip_file, "visio/pages/_rels/pages.xml.rels")
            if page_rels_tree:
                first_rel = page_rels_tree.find('.//{*}Relationship')
                if first_rel is not None:
                    page_xml_path = f"visio/pages/{first_rel.get('Target')}"
                    page_tree = self._get_xml_tree(zip_file, page_xml_path)
                    if page_tree:
                        # Look for PageSheet in the page
                        page_sheet = page_tree.find('.//v:PageSheet', self.namespaces)
                        if page_sheet is not None:
                            width_cell = page_sheet.find('.//v:Cell[@N="PageWidth"]', self.namespaces)
                            height_cell = page_sheet.find('.//v:Cell[@N="PageHeight"]', self.namespaces)
                            
                            if width_cell is not None and height_cell is not None:
                                # Visio stores dimensions in inches
                                width_inches = float(width_cell.get('V', '8.5'))
                                height_inches = float(height_cell.get('V', '11'))
                                self.page_width = width_inches * self.INCHES_TO_PIXELS
                                self.page_height = height_inches * self.INCHES_TO_PIXELS
                                print(f"Page size: {width_inches}\" x {height_inches}\"")
                                return True
            
            # Fallback to pages.xml
            pages_tree = self._get_xml_tree(zip_file, "visio/pages/pages.xml")
            if pages_tree:
                page_sheet = pages_tree.find('.//v:PageSheet', self.namespaces)
                if page_sheet is not None:
                    width_cell = page_sheet.find('.//v:Cell[@N="PageWidth"]', self.namespaces)
                    height_cell = page_sheet.find('.//v:Cell[@N="PageHeight"]', self.namespaces)

                    if width_cell is not None and height_cell is not None:
                        width_inches = float(width_cell.get('V', '8.5'))
                        height_inches = float(height_cell.get('V', '11'))
                        self.page_width = width_inches * self.INCHES_TO_PIXELS
                        self.page_height = height_inches * self.INCHES_TO_PIXELS
                        return True
                        
        except Exception as e:
            print(f"Warning: Error parsing page dimensions: {e}", file=sys.stderr)
        
        print("Using default page dimensions (8.5 x 11 inches)", file=sys.stderr)
        return True

    def _parse_custom_properties(self, master_tree):
        """Enhanced custom properties parsing."""
        custom_props = {}
        
        # Find all Property sections
        prop_sections = master_tree.findall('.//v:Section[@N="Property"]', self.namespaces)
        
        for section in prop_sections:
            rows = section.findall('.//v:Row', self.namespaces)
            
            for row in rows:
                prop_name = row.get('N')
                
                if prop_name:
                    prop_data = {
                        'name': prop_name,
                        'value': '',
                        'prompt': '',
                        'label': '',
                        'format': '',
                        'sortKey': '',
                        'type': '0',
                        'invisible': 'false',
                        'verify': 'false',
                        'dataLinked': 'false',
                        'langID': '1033',
                        'calendar': '0'
                    }
                    
                    for cell in row.findall('.//v:Cell', self.namespaces):
                        cell_name = cell.get('N')
                        cell_value = cell.get('V', '')
                        
                        if cell_name == 'Value':
                            prop_data['value'] = cell_value
                        elif cell_name == 'Prompt':
                            prop_data['prompt'] = cell_value
                        elif cell_name == 'Label':
                            prop_data['label'] = cell_value
                        elif cell_name == 'Format':
                            prop_data['format'] = cell_value
                        elif cell_name == 'SortKey':
                            prop_data['sortKey'] = cell_value
                        elif cell_name == 'Type':
                            prop_data['type'] = cell_value
                        elif cell_name == 'Invisible':
                            prop_data['invisible'] = 'true' if cell_value == '1' else 'false'
                        elif cell_name == 'Verify':
                            prop_data['verify'] = 'true' if cell_value == '1' else 'false'
                        elif cell_name == 'DataLinked':
                            prop_data['dataLinked'] = 'true' if cell_value == '1' else 'false'
                        elif cell_name == 'LangID':
                            prop_data['langID'] = cell_value
                        elif cell_name == 'Calendar':
                            prop_data['calendar'] = cell_value
                    
                    custom_props[prop_name] = prop_data
        
        return custom_props

    def _parse_masters(self, zip_file):
        """Enhanced master parsing with better geometry handling."""
        # Parse master relationships
        rels_tree = self._get_xml_tree(zip_file, "visio/masters/_rels/masters.xml.rels")
        if rels_tree:
            for rel in rels_tree.findall('.//{*}Relationship'):
                self.master_rel_map[rel.get('Id')] = rel.get('Target')
        
        # Parse masters.xml
        masters_tree = self._get_xml_tree(zip_file, "visio/masters/masters.xml")
        if not masters_tree: 
            print("Warning: No masters.xml found", file=sys.stderr)
            return

        for master in masters_tree.findall('.//v:Master', self.namespaces):
            master_id = master.get('ID')
            master_name = master.get('Name', f'Master_{master_id}')
            
            rel_elem = master.find('.//v:Rel', self.namespaces)
            if rel_elem is not None:
                rel_id = rel_elem.get(f"{{{self.namespaces['r']}}}id")
                if rel_id in self.master_rel_map:
                    master_file_path = f"visio/masters/{self.master_rel_map[rel_id]}"
                    master_tree = self._get_xml_tree(zip_file, master_file_path)
                    if master_tree:
                        geometry_data = self._parse_master_geometry(master_tree)
                        custom_props = self._parse_custom_properties(master_tree)
                        
                        self.masters[master_id] = {
                            'name': master_name,
                            **geometry_data,
                            'custom_props': custom_props
                        }

    def _parse_master_geometry(self, master_tree):
        """Enhanced geometry parsing with better path generation."""
        path_data = ""
        
        # Get master dimensions from XForm section
        xform_section = master_tree.find('.//v:Section[@N="XFormOut"]', self.namespaces)
        if xform_section is None:
            # Try alternative location
            xform_section = master_tree.find('.//v:Section[@N="XForm"]', self.namespaces)
        
        width = 1.0
        height = 1.0
        
        if xform_section is not None:
            width_cell = xform_section.find('.//v:Cell[@N="Width"]', self.namespaces)
            height_cell = xform_section.find('.//v:Cell[@N="Height"]', self.namespaces)
            
            if width_cell is not None:
                width = float(width_cell.get('V', '1'))
            if height_cell is not None:
                height = float(height_cell.get('V', '1'))

        # Parse geometry sections
        geom_sections = master_tree.findall('.//v:Section[@N="Geometry"]', self.namespaces)
        
        if not geom_sections:
            # Try alternative geometry section names
            geom_sections = master_tree.findall('.//v:Section[starts-with(@N,"Geometry")]', self.namespaces)
        
        for geom_idx, geom in enumerate(geom_sections):
            current_path = ""
            last_x, last_y = 0, 0
            
            rows = geom.findall('.//v:Row', self.namespaces)
            
            # Sort rows by index if available
            try:
                rows.sort(key=lambda r: int(r.get('IX', '0')))
            except:
                pass
            
            for row in rows:
                row_type = row.get('T')
                
                if row_type in ['MoveTo', 'LineTo', 'ArcTo', 'EllipticalArcTo']:
                    x_cell = row.find('v:Cell[@N="X"]', self.namespaces)
                    y_cell = row.find('v:Cell[@N="Y"]', self.namespaces)

                    if x_cell is None or y_cell is None: 
                        continue

                    # Enhanced coordinate parsing
                    try:
                        x_val = x_cell.get('V', '0')
                        x_formula = x_cell.get('F', '')
                        
                        if x_formula:
                            context = {'width': width, 'height': height}
                            x = self._evaluate_formula(x_formula, context)
                        else:
                            x = float(x_val)
                        
                        y_val = y_cell.get('V', '0')
                        y_formula = y_cell.get('F', '')
                        
                        if y_formula:
                            context = {'width': width, 'height': height}
                            y = self._evaluate_formula(y_formula, context)
                        else:
                            y = float(y_val)
                        
                    except (ValueError, TypeError):
                        x, y = last_x, last_y
                    
                    # Convert to SVG coordinates (Visio Y increases upward, SVG downward)
                    svg_x = x * self.INCHES_TO_PIXELS
                    svg_y = (height - y) * self.INCHES_TO_PIXELS
                    
                    # Generate path commands
                    if row_type == "MoveTo":
                        current_path += f"M {svg_x:.2f} {svg_y:.2f} "
                    elif row_type == "LineTo":
                        current_path += f"L {svg_x:.2f} {svg_y:.2f} "
                    elif row_type == "ArcTo":
                        # Enhanced arc handling
                        current_path += f"L {svg_x:.2f} {svg_y:.2f} "  # Simplified for now
                    elif row_type == "EllipticalArcTo":
                        current_path += f"L {svg_x:.2f} {svg_y:.2f} "  # Simplified for now
                    
                    last_x, last_y = x, y
                    
                elif row_type == "Ellipse":
                    # Create ellipse
                    cx = width / 2 * self.INCHES_TO_PIXELS
                    cy = height / 2 * self.INCHES_TO_PIXELS
                    rx = width / 2 * self.INCHES_TO_PIXELS
                    ry = height / 2 * self.INCHES_TO_PIXELS
                    current_path = f"M {cx-rx:.2f} {cy} A {rx:.2f} {ry:.2f} 0 1 1 {cx+rx:.2f} {cy} A {rx:.2f} {ry:.2f} 0 1 1 {cx-rx:.2f} {cy} Z"
                    break  # Ellipse is complete shape
            
            # Check if path should be closed
            no_fill_cell = geom.find('.//v:Cell[@N="NoFill"]', self.namespaces)
            no_line_cell = geom.find('.//v:Cell[@N="NoLine"]', self.namespaces)
            
            should_close = True
            if no_fill_cell is not None and no_fill_cell.get('V') == '1':
                should_close = False
            
            if current_path.strip() and should_close:
                if not current_path.strip().endswith('Z'):
                    current_path += "Z "
            
            path_data += current_path + " "
        
        # If no geometry found, create a default rectangle
        if not path_data.strip():
            w_px = width * self.INCHES_TO_PIXELS
            h_px = height * self.INCHES_TO_PIXELS
            path_data = f"M 0 0 L {w_px:.2f} 0 L {w_px:.2f} {h_px:.2f} L 0 {h_px:.2f} Z"
        
        return {
            "path": path_data.strip(), 
            "width": width, 
            "height": height
        }
    
    def _get_cell_value(self, element, cell_name, default=0.0, context=None):
        """Enhanced cell value extraction with formula support."""
        cell = element.find(f'.//v:Cell[@N="{cell_name}"]', self.namespaces)
        if cell is not None:
            # Check for formula first
            formula = cell.get('F', '')
            if formula:
                return self._evaluate_formula(formula, context)
            
            # Otherwise get direct value
            value = cell.get('V', str(default))
            try:
                return float(value)
            except ValueError:
                return default
        return default

    def _parse_page_shapes(self, page_tree):
        """Enhanced shape parsing with better text and positioning."""
        shapes_found = 0
        
        for shape in page_tree.findall('.//v:Shape', self.namespaces):
            shape_id = shape.get('ID')
            master_id = shape.get('Master')
            shape_type = shape.get('Type', 'Shape')
            
            # Skip connectors for now, handle them separately
            if shape_type == 'Foreign':
                continue
            
            # Enhanced text parsing
            text_content = self._extract_shape_text(shape)
            
            # Get shape transform data with context for formula evaluation
            context = {
                'width': 1.0,
                'height': 1.0,
                'pin_x': 0.0,
                'pin_y': 0.0
            }
            
            width = self._get_cell_value(shape, "Width", 1.0, context)
            height = self._get_cell_value(shape, "Height", 1.0, context)
            
            context.update({'width': width, 'height': height})
            
            pin_x = self._get_cell_value(shape, "PinX", 0.0, context)
            pin_y = self._get_cell_value(shape, "PinY", 0.0, context)
            loc_pin_x = self._get_cell_value(shape, "LocPinX", width/2, context)
            loc_pin_y = self._get_cell_value(shape, "LocPinY", height/2, context)
            angle = self._get_cell_value(shape, "Angle", 0.0, context)
            
            # Get fill and line properties
            fill_foregnd = self._get_shape_fill_color(shape)
            line_color = self._get_shape_line_color(shape)
            line_weight = self._get_cell_value(shape, "LineWeight", 1.0, context)
            
            self.shapes[shape_id] = {
                "id": shape_id,
                "master_id": master_id,
                "type": shape_type,
                "width": width,
                "height": height,
                "pin_x": pin_x,
                "pin_y": pin_y,
                "loc_pin_x": loc_pin_x,
                "loc_pin_y": loc_pin_y,
                "angle": angle,
                "text": text_content,
                "fill_color": fill_foregnd,
                "line_color": line_color,
                "line_weight": line_weight
            }
            shapes_found += 1
        
        self._parse_connectors(page_tree)
        return shapes_found > 0

    def _extract_shape_text(self, shape_element):
        """Enhanced text extraction from shape."""
        text_content = ""
        
        # Look for Text element
        text_elem = shape_element.find('.//v:Text', self.namespaces)
        if text_elem is not None:
            if text_elem.text:
                text_content = text_elem.text.strip()
            else:
                # Handle nested text formatting elements
                for child in text_elem.iter():
                    if child.text:
                        text_content += child.text
                    if child.tail:
                        text_content += child.tail
                text_content = text_content.strip()
        
        return text_content

    def _get_shape_fill_color(self, shape_element):
        """Extract fill color from shape."""
        fill_cell = shape_element.find('.//v:Cell[@N="FillForegnd"]', self.namespaces)
        if fill_cell is not None:
            color_value = fill_cell.get('V', '1')  # Default white
            return self._convert_visio_color(color_value)
        return "white"

    def _get_shape_line_color(self, shape_element):
        """Extract line color from shape."""
        line_cell = shape_element.find('.//v:Cell[@N="LineColor"]', self.namespaces)
        if line_cell is not None:
            color_value = line_cell.get('V', '0')  # Default black
            return self._convert_visio_color(color_value)
        return "black"

    def _convert_visio_color(self, color_value):
        """Convert Visio color value to CSS color."""
        try:
            # Visio stores colors as integers
            color_int = int(float(color_value))
            
            # Extract RGB components
            blue = (color_int >> 16) & 0xFF
            green = (color_int >> 8) & 0xFF
            red = color_int & 0xFF
            
            return f"rgb({red},{green},{blue})"
        except:
            return "black"

    def _parse_connectors(self, page_tree):
        """Enhanced connector parsing."""
        connects_section = page_tree.find('.//v:Connects', self.namespaces)
        if connects_section is None: 
            return

        for conn in connects_section.findall('.//v:Connect', self.namespaces):
            from_sheet = conn.get("FromSheet")
            to_sheet = conn.get("ToSheet")
            from_cell = conn.get("FromCell")
            to_cell = conn.get("ToCell")

            if from_sheet and to_sheet:
                if from_sheet not in self.connectors:
                    self.connectors[from_sheet] = {"id": from_sheet, "connections": []}
                
                conn_type = "start" if from_cell in ["BeginX", "Begin"] else "end"
                
                self.connectors[from_sheet]["connections"].append({
                    "to_sheet": to_sheet,
                    "to_cell": to_cell,
                    "from_cell": from_cell,
                    "type": conn_type
                })

    def _escape_xml(self, text):
        """Escapes special characters for XML/SVG."""
        if not text:
            return ""
        return html.escape(str(text), quote=True)

    def _generate_custom_props_data(self, custom_props):
        """Generates custom properties as data attributes for SVG."""
        if not custom_props:
            return ""
        
        data_attrs = []
        for prop_name, prop_data in custom_props.items():
            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', prop_name.lower())
            if prop_data.get('value'):
                data_attrs.append(f'data-{safe_name}="{self._escape_xml(prop_data["value"])}"')
            if prop_data.get('label'):
                data_attrs.append(f'data-{safe_name}-label="{self._escape_xml(prop_data["label"])}"')
            if prop_data.get('type'):
                data_attrs.append(f'data-{safe_name}-type="{self._escape_xml(prop_data["type"])}"')
        
        return " " + " ".join(data_attrs) if data_attrs else ""

    def _generate_svg_content(self):
        """Enhanced SVG content generation with better rendering."""
        svg_elements = []

        # Render Shapes
        for shape_id, shape_data in self.shapes.items():
            # Skip connector shapes (they're handled separately)
            if shape_id in self.connectors: 
                continue

            master = self.masters.get(shape_data['master_id'])
            
            # Calculate accurate positioning
            shape_width = shape_data['width'] * self.INCHES_TO_PIXELS
            shape_height = shape_data['height'] * self.INCHES_TO_PIXELS
            
            # Visio positioning: PinX/PinY is shape center, LocPinX/LocPinY is local pin within shape
            pin_x = shape_data['pin_x'] * self.INCHES_TO_PIXELS
            pin_y = shape_data['pin_y'] * self.INCHES_TO_PIXELS
            loc_pin_x = shape_data['loc_pin_x'] * self.INCHES_TO_PIXELS
            loc_pin_y = shape_data['loc_pin_y'] * self.INCHES_TO_PIXELS
            
            # Convert Visio coordinates to SVG coordinates
            x = pin_x - loc_pin_x
            y = self.page_height - pin_y - (shape_height - loc_pin_y)

            # Build transforms
            transforms = [f'translate({x:.2f},{y:.2f})']
            
            if shape_data['angle'] != 0:
                # Rotate around the local pin point
                angle_deg = -math.degrees(shape_data['angle'])  # Convert to SVG coordinate system
                transforms.append(f'rotate({angle_deg:.2f},{loc_pin_x:.2f},{loc_pin_y:.2f})')
            
            transform_attr = f'transform="{" ".join(transforms)}"'
            
            # Generate custom properties
            custom_props_attrs = ""
            if master and master.get('custom_props'):
                custom_props_attrs = self._generate_custom_props_data(master['custom_props'])
            
            # Create shape group
            group_attrs = [
                f'id="shape-{shape_id}"',
                f'class="visio-shape"',
                transform_attr
            ]
            
            group = [f'\t<g {" ".join(group_attrs)}{custom_props_attrs}>']
            
            # Add metadata
            title = self._escape_xml(shape_data["text"] or f"Shape {shape_id}")
            group.append(f'\t\t<title>{title}</title>')
            
            if shape_data['text']:
                group.append(f'\t\t<desc>{self._escape_xml(shape_data["text"])}</desc>')
            
            # Render geometry
            if master and master.get('path'):
                # Calculate scaling from master to instance
                master_width = master.get('width', 1)
                master_height = master.get('height', 1)
                scale_x = shape_width / (master_width * self.INCHES_TO_PIXELS) if master_width > 0 else 1
                scale_y = shape_height / (master_height * self.INCHES_TO_PIXELS) if master_height > 0 else 1
                
                path_attrs = [
                    f'd="{master["path"]}"',
                    f'stroke="{shape_data["line_color"]}"',
                    f'stroke-width="{shape_data["line_weight"]:.1f}"',
                    f'fill="{shape_data["fill_color"]}"',
                    'fill-opacity="0.8"'
                ]
                
                if abs(scale_x - 1) > 0.001 or abs(scale_y - 1) > 0.001:
                    path_attrs.append(f'transform="scale({scale_x:.3f},{scale_y:.3f})"')
                
                group.append(f'\t\t<path {" ".join(path_attrs)}/>')
            else:
                # Default rectangle
                rect_attrs = [
                    f'width="{shape_width:.2f}"',
                    f'height="{shape_height:.2f}"',
                    f'stroke="{shape_data["line_color"]}"',
                    f'stroke-width="{shape_data["line_weight"]:.1f}"',
                    f'fill="{shape_data["fill_color"]}"',
                    'fill-opacity="0.8"'
                ]
                group.append(f'\t\t<rect {" ".join(rect_attrs)}/>')

            # Add text if present
            if shape_data['text']:
                text_x = shape_width / 2
                text_y = shape_height / 2
                text_attrs = [
                    f'x="{text_x:.2f}"',
                    f'y="{text_y:.2f}"',
                    'text-anchor="middle"',
                    'dominant-baseline="central"',
                    'fill="black"',
                    'font-family="Arial, sans-serif"',
                    'font-size="10"'
                ]
                group.append(f'\t\t<text {" ".join(text_attrs)}>{self._escape_xml(shape_data["text"])}</text>')
            
            group.append('\t</g>')
            svg_elements.append('\n'.join(group))

        # Render Connectors
        for conn_id, conn_data in self.connectors.items():
            start_conn = next((c for c in conn_data["connections"] if c["type"] == "start"), None)
            end_conn = next((c for c in conn_data["connections"] if c["type"] == "end"), None)
            
            if start_conn and end_conn:
                from_shape = self.shapes.get(start_conn['to_sheet'])
                to_shape = self.shapes.get(end_conn['to_sheet'])

                if from_shape and to_shape:
                    # Calculate connection points more accurately
                    x1 = from_shape['pin_x'] * self.INCHES_TO_PIXELS
                    y1 = self.page_height - (from_shape['pin_y'] * self.INCHES_TO_PIXELS)
                    x2 = to_shape['pin_x'] * self.INCHES_TO_PIXELS
                    y2 = self.page_height - (to_shape['pin_y'] * self.INCHES_TO_PIXELS)
                    
                    line_attrs = [
                        f'id="connector-{conn_id}"',
                        f'x1="{x1:.2f}"',
                        f'y1="{y1:.2f}"',
                        f'x2="{x2:.2f}"',
                        f'y2="{y2:.2f}"',
                        'stroke="black"',
                        'stroke-width="1"',
                        'marker-end="url(#arrowhead)"',
                        'class="visio-connector"'
                    ]
                    svg_elements.append(f'\t<line {" ".join(line_attrs)}/>')
        
        return "\n".join(svg_elements)

    def convert(self, vsdx_path, svg_path):
        """
        Enhanced conversion method with better error handling and progress reporting.
        
        Args:
            vsdx_path (str): Path to the input .vsdx file.
            svg_path (str): Path to the output .svg file.
        """
        # Validate input file
        if not os.path.exists(vsdx_path):
            raise FileNotFoundError(f"Input file does not exist: {vsdx_path}")
        
        if not vsdx_path.lower().endswith('.vsdx'):
            raise ValueError("Input file must be a .vsdx file")
        
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(svg_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        print(f"Opening VSDX file: {vsdx_path}")
        
        try:
            with zipfile.ZipFile(vsdx_path, 'r') as zip_file:
                # Debug: Show ZIP structure
                zip_contents = zip_file.namelist()
                print(f"ZIP contains {len(zip_contents)} files")
                
                # Check for required files
                required_files = [
                    "visio/pages/_rels/pages.xml.rels",
                    "visio/masters/masters.xml",
                    "[Content_Types].xml"
                ]
                
                missing_files = [f for f in required_files if f not in zip_contents]
                if missing_files:
                    print(f"Warning: Missing expected files: {missing_files}", file=sys.stderr)
                
                # 1. Parse page dimensions
                print("Parsing page dimensions...")
                self._parse_page_dimensions(zip_file)
                print(f"Page dimensions: {self.page_width:.0f} x {self.page_height:.0f} px")
                
                # 2. Find and parse the first page
                page_rels_tree = self._get_xml_tree(zip_file, "visio/pages/_rels/pages.xml.rels")
                if not page_rels_tree:
                    # Try alternative location
                    page_rels_tree = self._get_xml_tree(zip_file, "visio/pages/_rels/page1.xml.rels")
                
                if not page_rels_tree:
                    raise FileNotFoundError("Could not find page relationships file.")

                first_rel = page_rels_tree.find('.//{*}Relationship')
                if first_rel is None:
                    raise ValueError("No page relationship found in pages.xml.rels.")
                
                page_xml_path = f"visio/pages/{first_rel.get('Target')}"
                print(f"Parsing page: {page_xml_path}")
                
                page_tree = self._get_xml_tree(zip_file, page_xml_path)
                if not page_tree:
                    raise FileNotFoundError(f"Could not parse page XML at {page_xml_path}")

                # 3. Parse masters
                print("Parsing master shapes...")
                self._parse_masters(zip_file)
                print(f"Found {len(self.masters)} master shapes")
                
                # Show master details
                for master_id, master_data in self.masters.items():
                    custom_props = master_data.get('custom_props', {})
                    master_name = master_data.get('name', f'Master_{master_id}')
                    print(f"  Master '{master_name}' (ID: {master_id}): {len(custom_props)} custom properties")
                
                # 4. Parse page shapes
                print("Parsing page shapes and connectors...")
                shapes_parsed = self._parse_page_shapes(page_tree)
                if not shapes_parsed:
                    print("Warning: No shapes found on the page", file=sys.stderr)
                
                print(f"Found {len(self.shapes)} shapes and {len(self.connectors)} connectors")
                
                # Show shape details
                shape_types = {}
                for shape_data in self.shapes.values():
                    shape_type = shape_data.get('type', 'Unknown')
                    shape_types[shape_type] = shape_types.get(shape_type, 0) + 1
                
                for shape_type, count in shape_types.items():
                    print(f"  {count} shapes of type: {shape_type}")

                # 5. Generate SVG content
                print("Generating SVG content...")
                svg_content = self._generate_svg_content()
                
                # 6. Create complete SVG with enhanced styling and definitions
                svg_definitions = '''  <defs>
    <style type="text/css"><![CDATA[
      .visio-shape { 
        cursor: pointer; 
      }
      .visio-connector { 
        pointer-events: none; 
        fill: none;
      }
      .visio-shape:hover { 
        opacity: 0.8; 
        filter: drop-shadow(2px 2px 4px rgba(0,0,0,0.3));
      }
      text {
        pointer-events: none;
        user-select: none;
      }
    ]]></style>
    <marker id="arrowhead" markerWidth="10" markerHeight="7" 
            refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill="black" />
    </marker>
  </defs>'''
                
                final_svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="{self.page_width:.0f}" height="{self.page_height:.0f}" 
     viewBox="0 0 {self.page_width:.0f} {self.page_height:.0f}" 
     xmlns="http://www.w3.org/2000/svg"
     xmlns:xlink="http://www.w3.org/1999/xlink">
{svg_definitions}
{svg_content}
</svg>'''

                # 7. Write output file
                with open(svg_path, 'w', encoding='utf-8') as f:
                    f.write(final_svg)
                
                print(f"Successfully converted to {svg_path}")
                
                # Show conversion summary
                print("\nConversion Summary:")
                print(f"  - Page size: {self.page_width/self.DPI:.2f}\" x {self.page_height/self.DPI:.2f}\"")
                print(f"  - Masters processed: {len(self.masters)}")
                print(f"  - Shapes converted: {len(self.shapes)}")
                print(f"  - Connectors found: {len(self.connectors)}")
                
                # Calculate file sizes
                input_size = os.path.getsize(vsdx_path)
                output_size = os.path.getsize(svg_path)
                print(f"  - Input size: {input_size:,} bytes")
                print(f"  - Output size: {output_size:,} bytes")
                
        except zipfile.BadZipFile:
            raise ValueError(f"Invalid or corrupted VSDX file: {vsdx_path}")
        except Exception as e:
            print(f"Error during conversion: {e}", file=sys.stderr)
            # Print more detailed error info for debugging
            import traceback
            traceback.print_exc()
            raise


def main():
    parser = argparse.ArgumentParser(
        description="Convert a Visio VSDX file to SVG format with enhanced accuracy and custom properties support.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Examples:
  python convert.py diagram.vsdx
  python convert.py diagram.vsdx output.svg
  python convert.py diagram.vsdx --verbose
        """
    )
    parser.add_argument("input", help="Input VSDX file path")
    parser.add_argument("output", nargs="?", help="Output SVG file path (default: same name as input with .svg extension)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    parser.add_argument("--version", action="version", version="VSDX to SVG Converter v2.0")
    
    args = parser.parse_args()
    
    # Set default output path if not provided
    if not args.output:
        base_name = os.path.splitext(args.input)[0]
        args.output = f"{base_name}.svg"
    
    # Validate arguments
    if args.input == args.output:
        print("Error: Input and output files cannot be the same.", file=sys.stderr)
        sys.exit(1)
    
    try:
        print("VSDX to SVG Converter v2.0")
        print("=" * 50)
        
        converter = VSDXToSVGConverter()
        converter.convert(args.input, args.output)
        
        print("=" * 50)
        print("Conversion completed successfully!")
        
    except KeyboardInterrupt:
        print("\nConversion cancelled by user.", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"File not found: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Invalid input: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()