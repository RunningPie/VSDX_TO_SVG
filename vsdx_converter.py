import zipfile
import xml.etree.ElementTree as ET
import re

class VsdxToSvgConverter:
    """
    A custom scraper and renderer to convert .vsdx files to SVG format.

    This class implements a pure Python solution to parse the XML structure
    of a .vsdx file and generate an SVG representation of the first page.

    Limitations:
    - Only converts the first page of the Visio document.
    - Handles basic shapes (rectangles, ellipses defined by geometry) and connectors.
    - Basic text rendering (no complex formatting).
    - Basic styling (stroke and fill are hardcoded for simplicity).
    - Does not handle complex gradients, themes, layers, or embedded images.
    """

    def __init__(self, vsdx_file_path):
        self.vsdx_file_path = vsdx_file_path
        self.namespaces = {
            'v': 'http://schemas.microsoft.com/office/visio/2012/main',
            'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
        }
        self.page_width = 0
        self.page_height = 0
        self.page_width_in_units = 0
        self.page_height_in_units = 0
        self.page_units = 'in'
        self.masters = {}
        self.shapes = {}
        self.connectors = {}
        self.page_xml = None
        self.master_rel_map = {}
        # Unit conversion factors (Visio units to pixels)
        self.unit_conversion = {
            'MM': 3.779527559,      # 1 MM = 3.78 pixels (96 DPI)
            'IN': 96.0,             # 1 IN = 96 pixels (96 DPI)
            'PT': 1.333333333,      # 1 PT = 1.33 pixels
            'CM': 37.795275591      # 1 CM = 37.8 pixels
        }
        # Style and color data
        self.styles = {}
        self.colors = {}
        # Drawing scale factor (crucial for proper sizing)
        self.drawing_scale = 1.0

    def _get_xml_tree(self, zip_file, xml_path):
        """Reads and parses an XML file from the zip archive."""
        try:
            with zip_file.open(xml_path) as xml_file:
                return ET.parse(xml_file)
        except KeyError:
            print(f"Warning: XML file not found at {xml_path}")
            return None

    def _parse_page_dimensions(self, zf):
        """Parse page dimensions from pages.xml instead of page1.xml."""
        print("Parsing page dimensions...")
        
        # Read pages.xml to get page dimensions
        pages_tree = self._get_xml_tree(zf, 'visio/pages/pages.xml')
        if not pages_tree:
            print("Error: Could not find pages.xml file.")
            return False
        
        # Find the PageSheet element in pages.xml
        page_sheet = pages_tree.find('.//v:PageSheet', self.namespaces)
        if page_sheet is None:
            print("Error: Could not find PageSheet element in pages.xml.")
            return False
        
        # Extract page dimensions from Cell elements
        page_width_cell = page_sheet.find('.//v:Cell[@N="PageWidth"]', self.namespaces)
        page_height_cell = page_sheet.find('.//v:Cell[@N="PageHeight"]', self.namespaces)
        
        # Get drawing scale (crucial for proper sizing)
        drawing_scale_cell = page_sheet.find('.//v:Cell[@N="DrawingScale"]', self.namespaces)
        if drawing_scale_cell is not None:
            self.drawing_scale = float(drawing_scale_cell.get('V', '1.0'))
            print(f"Drawing scale: {self.drawing_scale}")
        
        if page_width_cell is not None and page_height_cell is not None:
            # Get values and units
            width_val = float(page_width_cell.get('V', '0'))
            height_val = float(page_height_cell.get('V', '0'))
            width_units = page_width_cell.get('U', 'IN')  # Default to inches
            height_units = page_height_cell.get('U', 'IN')
            
            # Store original dimensions and units
            self.page_width_in_units = width_val
            self.page_height_in_units = height_val
            self.page_units = width_units.lower()

            # Convert to pixels
            self.page_width = width_val * self.unit_conversion.get(width_units, 96.0)
            self.page_height = height_val * self.unit_conversion.get(height_units, 96.0)
            
            print(f"Page dimensions: {width_val} {width_units} x {height_val} {height_units} = {self.page_width:.1f} x {self.page_height:.1f} pixels")
            return True
        else:
            print("Error: Could not find PageWidth or PageHeight cells in PageSheet.")
            return False

    def _parse_masters(self, zf):
        """Parses all master shape definitions."""
        print("Parsing master shapes...")
        # First, find the relationship mapping for masters
        rel_ns = {'rel': 'http://schemas.openxmlformats.org/package/2006/relationships'}
        rels_tree = self._get_xml_tree(zf, 'visio/masters/_rels/masters.xml.rels')
        if rels_tree:
            for rel in rels_tree.findall('rel:Relationship', rel_ns):
                self.master_rel_map[rel.get('Id')] = rel.get('Target')

        # Now parse the master files
        masters_tree = self._get_xml_tree(zf, 'visio/masters/masters.xml')
        if not masters_tree:
            return

        print(f"Found {len(masters_tree.findall('v:Master', self.namespaces))} master definitions")
        
        for master in masters_tree.findall('v:Master', self.namespaces):
            master_id = master.get('ID')
            # Look for the Rel child element and get its r:id attribute
            rel_elem = master.find('v:Rel', self.namespaces)
            rel_id = rel_elem.get('{' + self.namespaces['r'] + '}id') if rel_elem is not None else None
            
            if rel_id and rel_id in self.master_rel_map:
                master_file_path = f"visio/masters/{self.master_rel_map[rel_id]}"
                master_tree = self._get_xml_tree(zf, master_file_path)
                if master_tree:
                    master_data = self._parse_master_geometry(master_tree)
                    self.masters[master_id] = master_data
                    print(f"Master {master_id}: {master_data}")
                    if master_data['path']:
                        print(f"Master {master_id}: Parsed geometry with path length {len(master_data['path'])}")
                    else:
                        print(f"Master {master_id}: No geometry path found")
            else:
                print(f"Master {master_id}: No relationship mapping found for {rel_id}")

    def _parse_master_geometry(self, master_tree):
        """Extracts geometry (as SVG path data) from a master shape XML."""
        # Look for Section elements with N="Geometry"
        geom_sections = master_tree.findall('.//v:Section[@N="Geometry"]', self.namespaces)
        print(f"Found {len(geom_sections)} geometry sections")
        print(f"Geom sections: {geom_sections}")
        if not geom_sections:
            return {'path': '', 'width': 1, 'height': 1} # Default if no geometry

        path_data = ""
        
        # Get width and height with units
        width_cell = master_tree.find('.//v:Cell[@N="Width"]', self.namespaces)
        height_cell = master_tree.find('.//v:Cell[@N="Height"]', self.namespaces)
        
        width = float(width_cell.get('V', '1') if width_cell is not None else '1')
        height = float(height_cell.get('V', '1') if height_cell is not None else '1')
        
        print(f"    Master dimensions: {width} x {height} (master units)")

        # Process each geometry section
        for geom_section in geom_sections:
            print(f"  Processing geometry section: {geom_section.get('IX', 'unknown')}")
            # Check if this section should be filled or just outlined
            no_fill = geom_section.findtext('.//v:NoFill', namespaces=self.namespaces) == '1'
            no_line = geom_section.findtext('.//v:NoLine', namespaces=self.namespaces) == '1'
            
            # Process each row in the geometry section
            rows = geom_section.findall('v:Row', self.namespaces)
            print(f"    Found {len(rows)} rows in this section")
            for row in rows:
                row_type = row.get('T')  # The type of geometry command
                print(f"      Row type: {row_type}")
                
                # Look for X and Y in Cell elements
                x_cell = row.find('v:Cell[@N="X"]', self.namespaces)
                y_cell = row.find('v:Cell[@N="Y"]', self.namespaces)
                
                x = x_cell.get('V') if x_cell is not None else None
                y = y_cell.get('V') if y_cell is not None else None
                x_units = x_cell.get('U') if x_cell is not None else None
                y_units = y_cell.get('U') if y_cell is not None else None
                x_formula = x_cell.get('F') if x_cell is not None else None
                y_formula = y_cell.get('F') if y_cell is not None else None
                
                print(f"      X: {x} {x_units} (F: {x_formula}), Y: {y} {y_units} (F: {y_formula})")
                
                if x and y:
                    # Convert Visio coordinates to SVG path coordinates
                    # Handle formulas if present
                    if x_formula and 'Width' in x_formula:
                        # X is relative to width (e.g., "Width*0" = left edge, "Width*1" = right edge)
                        x_val = float(x) * width
                    else:
                        x_val = float(x)
                        
                    if y_formula and 'Height' in y_formula:
                        # Y is relative to height (e.g., "Height*0.5" = center)
                        y_val = float(y) * height
                    else:
                        y_val = float(y)
                    
                    # Convert to SVG coordinates (invert Y axis)
                    # Visio uses bottom-left origin, SVG uses top-left origin
                    px = x_val
                    py = height - y_val
                    
                    print(f"        Calculated: px={px:.1f}, py={py:.1f}")
                    
                    if row_type == 'MoveTo':
                        path_data += f"M {px} {py} "
                    elif row_type == 'LineTo':
                        path_data += f"L {px} {py} "
                    elif row_type == 'EllipticalArcTo':
                        # Handle elliptical arcs if present
                        path_data += f"A {px} {py} 0 0 1 {px} {py} "
                    elif row_type == 'ArcTo':
                        # Handle arcs if present
                        path_data += f"A {px} {py} 0 0 1 {px} {py} "
            
            # Close the path if it's a filled shape
            if not no_fill and path_data:
                path_data += "Z "

        return {'path': path_data.strip(), 'width': width, 'height': height}


    def _parse_page_shapes(self):
        """Parses all shapes on the first page."""
        print("Parsing page shapes...")
        
        # Parse shapes from page1.xml
        for shape in self.page_xml.findall('.//v:Shape', self.namespaces):
            shape_id = shape.get('ID')
            master_id = shape.get('Master')
            
            # Parse additional shape attributes
            line_style = shape.get('LineStyle')
            fill_style = shape.get('FillStyle')
            text_style = shape.get('TextStyle')
            name_u = shape.get('NameU')
            name = shape.get('Name')
            unique_id = shape.get('UniqueID')
            
            # Try to get transform data from Xf element first
            xf = shape.find('v:Xf', self.namespaces)
            if xf is not None:
                # Shape has explicit transform data
                width_val = float(xf.findtext('v:Width', namespaces=self.namespaces) or '0.1')
                height_val = float(xf.findtext('v:Height', namespaces=self.namespaces) or '0.1')
                pin_x_val = float(xf.findtext('v:PinX', namespaces=self.namespaces) or '0')
                pin_y_val = float(xf.findtext('v:PinY', namespaces=self.namespaces) or '0')
                angle = float(xf.findtext('v:Angle', namespaces=self.namespaces) or '0')
                
                # Convert to pixels (assuming inches)
                width = width_val * 96.0
                height = height_val * 96.0
                pin_x = pin_x_val * 96.0
                pin_y = pin_y_val * 96.0
            else:
                # Try to get data from Cell elements - look for specific Cell names
                width_cell = shape.find('.//v:Cell[@N="Width"]', self.namespaces)
                height_cell = shape.find('.//v:Cell[@N="Height"]', self.namespaces)
                pin_x_cell = shape.find('.//v:Cell[@N="PinX"]', self.namespaces)
                pin_y_cell = shape.find('.//v:Cell[@N="PinY"]', self.namespaces)
                angle_cell = shape.find('.//v:Cell[@N="Angle"]', self.namespaces)
                
                # Get values and units
                width_val = float(width_cell.get('V', '0.1') if width_cell is not None else '0.1')
                height_val = float(height_cell.get('V', '0.1') if height_cell is not None else '0.1')
                pin_x_val = float(pin_x_cell.get('V', '0') if pin_x_cell is not None else '0')
                pin_y_val = float(pin_y_cell.get('V', '0') if pin_y_cell is not None else '0')
                angle = float(angle_cell.get('V', '0') if angle_cell is not None else '0')
                
                # Get units (default to inches if not specified)
                width_units = width_cell.get('U', 'IN') if width_cell is not None else 'IN'
                height_units = height_cell.get('U', 'IN') if height_cell is not None else 'IN'
                pin_x_units = pin_x_cell.get('U', 'IN') if pin_x_cell is not None else 'IN'
                pin_y_units = pin_y_cell.get('U', 'IN') if pin_y_cell is not None else 'IN'
                
                # Convert to pixels
                width = width_val * self.unit_conversion.get(width_units, 96.0)
                height = height_val * self.unit_conversion.get(height_units, 96.0)
                pin_x = pin_x_val * self.unit_conversion.get(pin_x_units, 96.0)
                pin_y = pin_y_val * self.unit_conversion.get(pin_y_units, 96.0)
            
            # Get text content
            text_elem = shape.find('.//v:Text', self.namespaces)
            text = ""
            text_style_details = {}
            if text_elem is not None:
                # Extract text from various text elements
                for text_part in text_elem.iter():
                    if text_part.text and text_part.text.strip():
                        text += text_part.text.strip() + " "
                text = text.strip()
                
                # Parse Character section for text styling
                char_sections = shape.findall('.//v:Section[@N="Character"]', self.namespaces)
                for char_section in char_sections:
                    for char_row in char_section.findall('v:Row', self.namespaces):
                        for cell in char_row.findall('v:Cell', self.namespaces):
                            cell_name = cell.get('N')
                            cell_value = cell.get('V')
                            if cell_name:
                                text_style_details[cell_name] = cell_value

            # Reset connector data for each shape
            is_connector = 'Connector' in (name_u or '')
            connector_data = None

            if is_connector:
                connector_data = {
                    'from_sheet': None,
                    'to_sheet': None
                }
                begin_x_cell = shape.find('.//v:Cell[@N="BeginX"]', self.namespaces)
                end_x_cell = shape.find('.//v:Cell[@N="EndX"]', self.namespaces)

                if begin_x_cell is not None and begin_x_cell.get('F'):
                    formula = begin_x_cell.get('F')
                    match = re.search(r'Sheet\.(\d+)!', formula)
                    if match:
                        connector_data['from_sheet'] = match.group(1)

                if end_x_cell is not None and end_x_cell.get('F'):
                    formula = end_x_cell.get('F')
                    match = re.search(r'Sheet\.(\d+)!', formula)
                    if match:
                        connector_data['to_sheet'] = match.group(1)
                
                if connector_data['from_sheet'] and connector_data['to_sheet']:
                    self.connectors[shape_id] = connector_data


            shape_data = {
                'id': shape_id,
                'master_id': master_id,
                'width': width,
                'height': height,
                'pin_x': pin_x,
                'pin_y': pin_y,
                'angle': angle,
                'text': text,
                'text_style_details': text_style_details,
                'line_style': line_style,
                'fill_style': fill_style,
                'text_style': text_style,
                'name_u': name_u,
                'name': name,
                'unique_id': unique_id
            }
            
            self.shapes[shape_id] = shape_data
        
        print(f"Parsed {len(self.shapes)} shapes and {len(self.connectors)} connectors")
        
        # Debug: Show some shape details
        for i, (shape_id, shape_data) in enumerate(list(self.shapes.items())[:5]):
            print(f"  Shape {shape_id}: master={shape_data['master_id']}, size={shape_data['width']:.3f}x{shape_data['height']:.3f}, pos=({shape_data['pin_x']:.3f}, {shape_data['pin_y']:.3f})")
        
        # Debug: Show connector details
        for i, (conn_id, conn_data) in enumerate(list(self.connectors.items())[:5]):
            print(f"  Connector {conn_id}: from={conn_data['from_sheet']}, to={conn_data['to_sheet']}")
        
        return True

    def _generate_svg_content(self):
        """Generates the SVG content from parsed data."""
        print("Generating SVG content...")
        svg_elements = []
        
        # Process regular shapes first
        for shape_id, shape_data in self.shapes.items():
            if shape_id in self.connectors:
                continue # Skip connectors for now

            master = self.masters.get(shape_data['master_id'])
            if not master or not master['path']:
                # If no master geometry,    draw a simple rectangle
                svg_path = f"M 0 0 L {shape_data['width']} 0 L {shape_data['width']} {shape_data['height']} L 0 {shape_data['height']} Z"
                print(f"Shape {shape_id}: Using default rectangle (no master geometry)")
            else:
                svg_path = master['path']
                print(f"Shape {shape_id}: Using master geometry from {shape_data['master_id']}")

            # Calculate position. Visio's PinX/PinY is the center of the shape.
            # SVG's x/y is the top-left corner.
            x = shape_data['pin_x'] - (shape_data['width'] / 2)
            y = self.page_height - (shape_data['pin_y'] + (shape_data['height'] / 2)) # Invert Y for SVG's top-left origin

            # Create a group for the shape and its text to apply transforms
            transform = f"translate({x}, {y})"
            if shape_data['angle'] != 0:
                # SVG rotates around the origin (0,0), so we translate to center for rotation
                rot_x = shape_data['width'] / 2
                rot_y = shape_data['height'] / 2
                transform += f" rotate({-shape_data['angle'] * 180 / 3.14159}, {rot_x}, {rot_y})"
            
            svg_elements.append(f'<g transform="{transform}">')
            
            # Scale the master path to the shape's actual size
            scale_x = shape_data['width'] / master['width'] if master and master['width'] != 0 else 1
            scale_y = shape_data['height'] / master['height'] if master and master['height'] != 0 else 1
            path_transform = f"scale({scale_x} {scale_y})"

            # Get styling for this shape
            style_info = self._get_shape_style(shape_data)
            
            # Create SVG path with proper styling
            svg_style = f"fill:{style_info['fill_color']};stroke:{style_info['line_color']};stroke-width:{style_info['line_weight']};"
            svg_elements.append(f'  <path d="{svg_path}" transform="{path_transform}" style="{svg_style}" />')

            if shape_data['text']:
                # Enhanced text styling using Character section details
                text_x = shape_data['width'] / 2
                text_y = shape_data['height'] / 2
                
                # Use text style details if available, otherwise use default style
                text_font = shape_data['text_style_details'].get('Font', style_info['text_font'])
                text_size = shape_data['text_style_details'].get('Size', style_info['text_size'])
                text_color = shape_data['text_style_details'].get('Color', style_info['text_color'])
                
                text_style = f"font-family:{text_font};font-size:{text_size}px;fill:{text_color};"
                svg_elements.append(f'  <text x="{text_x}" y="{text_y}" dominant-baseline="middle" text-anchor="middle" style="{text_style}">{shape_data["text"]}</text>')
            
            svg_elements.append('</g>')

        # Process connectors with enhanced details
        for conn_id, conn_data in self.connectors.items():
            # Debug: Print full connector data
            print(f"Processing Connector {conn_id}: {conn_data}")
            
            # Try to find connection points with specific IX or T attributes
            from_point = None
            to_point = None
            
            for point in conn_data.get('connection_points', []):
                # Look for connection points with specific characteristics
                if point.get('IX') == '1':
                    from_point = point
                elif point.get('IX') == '2':
                    to_point = point
            
            # If we can't find points by IX, try other methods
            if not (from_point and to_point):
                print(f"Warning: Could not find both connection points for connector {conn_id}")
                continue
            
            # Try to find the connected shapes
            from_shape = None
            to_shape = None
            
            # Look for Y coordinates or other identifying information
            if from_point and 'Y' in from_point['cells']:
                from_y = float(from_point['cells']['Y']['value'])
                for shape_id, shape_data in self.shapes.items():
                    # Check if shape's Y coordinate is close to the connection point
                    if abs(shape_data['pin_y'] - from_y) < 0.1:
                        from_shape = shape_data
                        break
            
            if to_point and 'Y' in to_point['cells']:
                to_y = float(to_point['cells']['Y']['value'])
                for shape_id, shape_data in self.shapes.items():
                    # Check if shape's Y coordinate is close to the connection point
                    if abs(shape_data['pin_y'] - to_y) < 0.1:
                        to_shape = shape_data
                        break
            
            # If we found both shapes, draw a connector
            if from_shape and to_shape:
                x1 = from_shape['pin_x']
                y1 = from_shape['pin_y']
                x2 = to_shape['pin_x']
                y2 = to_shape['pin_y']
                
                print(f"Drawing connector from ({x1:.1f}, {y1:.1f}) to ({x2:.1f}, {y2:.1f})")
                
                # Enhanced connector styling
                connector_style = "stroke:#000000;stroke-width:1;"
                
                # Check if there are additional connection point details
                if conn_data.get('connection_points'):
                    # You could use connection point details to modify the line style
                    # For example, check for line weight or color in connection details
                    pass
                
                svg_elements.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" style="{connector_style}" />')
            else:
                print(f"Warning: Connector {conn_id} could not find both connected shapes")
                # Optionally, print out the Y coordinates we were looking for
                if from_point and 'Y' in from_point['cells']:
                    print(f"  From Y: {from_point['cells']['Y']['value']}")
                if to_point and 'Y' in to_point['cells']:
                    print(f"  To Y: {to_point['cells']['Y']['value']}")
                print(f"  Available shape Y coordinates: {[shape['pin_y'] for shape in self.shapes.values()]}")

        return "\n".join(svg_elements)

    def _normalize_coordinates(self):
        """
        Normalize shape coordinates to fit within a standard page layout.
        This mimics Visio's coordinate transformation.
        """
        if not self.shapes:
            return

        # Find coordinate ranges
        min_x = min(shape['pin_x'] - shape['width']/2 for shape in self.shapes.values())
        max_x = max(shape['pin_x'] + shape['width']/2 for shape in self.shapes.values())
        min_y = min(shape['pin_y'] - shape['height']/2 for shape in self.shapes.values())
        max_y = max(shape['pin_y'] + shape['height']/2 for shape in self.shapes.values())

        # Calculate scaling factors
        page_width = 1190.55   # Standard A4 landscape width in points
        page_height = 841.89   # Standard A4 landscape height in points
        
        x_scale = page_width / (max_x - min_x)
        y_scale = page_height / (max_y - min_y)
        scale = min(x_scale, y_scale)

        # Normalize each shape's coordinates
        for shape_id, shape_data in self.shapes.items():
            # Center the shape relative to the page
            shape_data['pin_x'] = (shape_data['pin_x'] - min_x) * scale
            shape_data['pin_y'] = (shape_data['pin_y'] - min_y) * scale
            
            # Scale shape dimensions
            shape_data['width'] *= scale
            shape_data['height'] *= scale

        # Update page dimensions to match normalized coordinates
        self.page_width = page_width
        self.page_height = page_height
        self.page_width_in_units = 16.5354  # A4 landscape width in inches
        self.page_height_in_units = 11.6929  # A4 landscape height in inches
        self.page_units = 'in'

    def convert(self):
        """Main conversion method."""
        try:
            with zipfile.ZipFile(self.vsdx_file_path, 'r') as zf:
                # First, parse page dimensions from pages.xml
                if not self._parse_page_dimensions(zf):
                    return None
                
                # Define the namespace for the relationships file, which has a default namespace
                rel_ns = {'rel': 'http://schemas.openxmlformats.org/package/2006/relationships'}
                
                # Find the relationship file for pages to locate the first page XML
                page_rels_tree = self._get_xml_tree(zf, 'visio/pages/_rels/pages.xml.rels')
                if page_rels_tree is None:
                    print("Error: Could not find page relationships file ('visio/pages/_rels/pages.xml.rels').")
                    return None

                # Find the first relationship target, which should be the first page (e.g., page1.xml)
                first_rel_node = page_rels_tree.find('rel:Relationship', rel_ns)
                if first_rel_node is None:
                    print("Error: No relationship found in pages.xml.rels file.")
                    return None
                
                page_path_target = first_rel_node.get('Target')
                if not page_path_target:
                    print("Error: Relationship node found but it has no Target attribute.")
                    return None

                page_xml_path = f"visio/pages/{page_path_target}"
                
                page_tree = self._get_xml_tree(zf, page_xml_path)
                if page_tree is None:
                    print(f"Error: Could not parse page XML at '{page_xml_path}'")
                    return None
                self.page_xml = page_tree.getroot()
                
                # Parse styles and colors first
                self._parse_colors(zf)
                self._parse_styles(zf)
                
                self._parse_masters(zf)
                
                # Check for failure in parsing page shapes before continuing
                if not self._parse_page_shapes():
                    return None # Stop conversion if page parsing fails
                
                # Normalize coordinates to match Visio's layout
                self._normalize_coordinates()
                
                svg_content = self._generate_svg_content()
                
                # Assemble the final SVG file
                svg_output = f'<svg width="{self.page_width_in_units}{self.page_units}" height="{self.page_height_in_units}{self.page_units}" viewBox="0 0 {self.page_width} {self.page_height}" xmlns="http://www.w3.org/2000/svg">\n'
                svg_output += svg_content
                svg_output += '\n</svg>'
                
                return svg_output

        except FileNotFoundError:
            print(f"Error: File not found at {self.vsdx_file_path}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _parse_colors(self, zf):
        """Parse color definitions from document.xml."""
        print("Parsing colors...")
        
        document_tree = self._get_xml_tree(zf, 'visio/document.xml')
        if not document_tree:
            print("Warning: Could not find document.xml for colors")
            return
        
        # Parse color entries
        for color_elem in document_tree.findall('.//v:ColorEntry', self.namespaces):
            color_id = color_elem.get('IX')
            rgb_value = color_elem.get('RGB')
            if color_id and rgb_value:
                self.colors[color_id] = rgb_value
                print(f"  Color {color_id}: {rgb_value}")
        
        print(f"Parsed {len(self.colors)} colors")

    def _parse_styles(self, zf):
        """Parse style definitions from document.xml with more comprehensive details."""
        print("Parsing styles...")
        
        document_tree = self._get_xml_tree(zf, 'visio/document.xml')
        if not document_tree:
            print("Warning: Could not find document.xml for styles")
            return
        
        # Parse color entries first
        self.colors = {}
        for color_elem in document_tree.findall('.//v:ColorEntry', self.namespaces):
            color_id = color_elem.get('IX')
            rgb_value = color_elem.get('RGB')
            if color_id and rgb_value:
                self.colors[color_id] = rgb_value
                print(f"  Color {color_id}: {rgb_value}")
        
        # Parse style sheets
        self.styles = {}
        for style_elem in document_tree.findall('.//v:StyleSheet', self.namespaces):
            style_id = style_elem.get('ID')
            name = style_elem.get('NameU', 'Unknown')
            
            if style_id:
                style_data = {
                    'id': style_id,
                    'name': name,
                    'line_style': style_elem.get('LineStyle'),
                    'fill_style': style_elem.get('FillStyle'),
                    'text_style': style_elem.get('TextStyle'),
                    'properties': {}
                }
                
                # Parse style properties from Cell elements
                for cell_elem in style_elem.findall('.//v:Cell', self.namespaces):
                    cell_name = cell_elem.get('N')
                    cell_value = cell_elem.get('V')
                    cell_formula = cell_elem.get('F')
                    
                    if cell_name and cell_value:
                        # Handle color references and themed values
                        if cell_name in ['LineColor', 'FillForegnd', 'FillBkgnd', 'Color']:
                            if cell_value.isdigit():
                                cell_value = self.colors.get(cell_value, cell_value)
                            elif cell_value == 'Themed':
                                cell_value = None  # Placeholder for themed colors
                        
                        style_data['properties'][cell_name] = {
                            'value': cell_value,
                            'formula': cell_formula,
                            'inherited': cell_formula == 'Inh'
                        }
                
                self.styles[style_id] = style_data
                print(f"  Style {style_id}: {name}")
        
        print(f"Parsed {len(self.colors)} colors and {len(self.styles)} styles")

    def _get_style_property(self, style_id, property_name, default_value=None):
        """Get a property value from a style, handling inheritance and themed values."""
        if style_id not in self.styles:
            return default_value
        
        style = self.styles[style_id]
        if property_name in style['properties']:
            prop = style['properties'][property_name]
            value = prop['value']
            
            # Handle inherited or themed values
            if prop['inherited'] or value is None:
                # Look for parent style
                parent_style_id = style.get('line_style') or style.get('fill_style') or style.get('text_style')
                if parent_style_id and parent_style_id != style_id:
                    return self._get_style_property(parent_style_id, property_name, default_value)
                return default_value
            
            return value
        
        return default_value

    def _get_shape_style(self, shape_data):
        """Get the complete styling for a shape with enhanced inheritance."""
        style_info = {
            'line_color': '#000000',      # Default black
            'line_weight': '1',           # Default 1px
            'fill_color': '#ffffff',      # Default white
            'text_color': '#000000',      # Default black
            'text_size': '12',            # Default 12px
            'text_font': 'Arial'          # Default Arial
        }
        
        # Get line style properties
        if 'line_style' in shape_data and shape_data['line_style']:
            line_style_id = shape_data['line_style']
            style_info['line_color'] = self._get_style_property(line_style_id, 'LineColor', '#000000')
            style_info['line_weight'] = self._get_style_property(line_style_id, 'LineWeight', '1')
        
        # Get fill style properties
        if 'fill_style' in shape_data and shape_data['fill_style']:
            fill_style_id = shape_data['fill_style']
            style_info['fill_color'] = self._get_style_property(fill_style_id, 'FillForegnd', '#ffffff')
        
        # Get text style properties
        if 'text_style' in shape_data and shape_data['text_style']:
            text_style_id = shape_data['text_style']
            style_info['text_color'] = self._get_style_property(text_style_id, 'Color', '#000000')
            style_info['text_size'] = self._get_style_property(text_style_id, 'Size', '12')
            style_info['text_font'] = self._get_style_property(text_style_id, 'Font', 'Arial')
        
        return style_info

# --- HOW TO USE THIS SCRIPT ---
if __name__ == '__main__':
    # 1. Replace this with the path to your .vsdx file
    input_vsdx_file = "diagram.vsdx"
    
    # 2. Replace this with your desired output file name
    output_svg_file = "output.svg"

    print(f"Starting conversion of '{input_vsdx_file}'...")
    
    converter = VsdxToSvgConverter(input_vsdx_file)
    svg_data = converter.convert()

    if svg_data:
        with open(output_svg_file, "w", encoding="utf-8") as f:
            f.write(svg_data)
        print(f"\nConversion successful! SVG saved to '{output_svg_file}'")
    else:
        print("\nConversion failed.")
