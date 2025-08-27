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
        self.masters = {}
        self.shapes = {}
        self.connectors = {}
        self.page_xml = None
        self.master_rel_map = {}

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
        
        if page_width_cell is not None and page_height_cell is not None:
            self.page_width = float(page_width_cell.get('V', '0'))
            self.page_height = float(page_height_cell.get('V', '0'))
            print(f"Page dimensions: {self.page_width} x {self.page_height}")
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
        width_units = width_cell.get('U') if width_cell is not None else None
        height_units = height_cell.get('U') if height_cell is not None else None
        
        print(f"    Master dimensions: {width} {width_units} x {height} {height_units}")

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
                    px = x_val
                    py = height - y_val
                    
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
            
            # Try to get transform data from Xf element first
            xf = shape.find('v:Xf', self.namespaces)
            if xf is not None:
                # Shape has explicit transform data
                width = float(xf.findtext('v:Width', namespaces=self.namespaces) or '0.1')
                height = float(xf.findtext('v:Height', namespaces=self.namespaces) or '0.1')
                pin_x = float(xf.findtext('v:PinX', namespaces=self.namespaces) or '0')
                pin_y = float(xf.findtext('v:PinY', namespaces=self.namespaces) or '0')
                angle = float(xf.findtext('v:Angle', namespaces=self.namespaces) or '0')
            else:
                # Try to get data from Cell elements - look for specific Cell names
                width_cell = shape.find('.//v:Cell[@N="Width"]', self.namespaces)
                height_cell = shape.find('.//v:Cell[@N="Height"]', self.namespaces)
                pin_x_cell = shape.find('.//v:Cell[@N="PinX"]', self.namespaces)
                pin_y_cell = shape.find('.//v:Cell[@N="PinY"]', self.namespaces)
                angle_cell = shape.find('.//v:Cell[@N="Angle"]', self.namespaces)
                
                width = float(width_cell.get('V', '0.1') if width_cell is not None else '0.1')
                height = float(height_cell.get('V', '0.1') if height_cell is not None else '0.1')
                pin_x = float(pin_x_cell.get('V', '0') if pin_x_cell is not None else '0')
                pin_y = float(pin_y_cell.get('V', '0') if pin_y_cell is not None else '0')
                angle = float(angle_cell.get('V', '0') if angle_cell is not None else '0')
            
            # Get text content
            text_elem = shape.find('.//v:Text', self.namespaces)
            text = ""
            if text_elem is not None:
                # Extract text from various text elements
                for text_part in text_elem.iter():
                    if text_part.text and text_part.text.strip():
                        text += text_part.text.strip() + " "
                text = text.strip()

            shape_data = {
                'id': shape_id,
                'master_id': master_id,
                'width': width,
                'height': height,
                'pin_x': pin_x,
                'pin_y': pin_y,
                'angle': angle,
                'text': text
            }

            # Check if it's a connector
            connects = shape.findall('v:Connect', self.namespaces)
            if connects:
                self.connectors[shape_id] = {
                    'from_sheet': connects[0].get('FromSheet'),
                    'to_sheet': connects[1].get('ToSheet') if len(connects) > 1 else None,
                    'from_cell': connects[0].get('FromCell'),
                    'to_cell': connects[1].get('ToCell') if len(connects) > 1 else None
                }
            
            self.shapes[shape_id] = shape_data
        
        print(f"Parsed {len(self.shapes)} shapes and {len(self.connectors)} connectors")
        
        # Debug: Show some shape details
        for i, (shape_id, shape_data) in enumerate(list(self.shapes.items())[:5]):
            print(f"  Shape {shape_id}: master={shape_data['master_id']}, size={shape_data['width']:.3f}x{shape_data['height']:.3f}, pos=({shape_data['pin_x']:.3f}, {shape_data['pin_y']:.3f})")
        
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
                # If no master geometry, draw a simple rectangle
                svg_path = f"M 0 0 L {shape_data['width']} 0 L {shape_data['width']} {shape_data['height']} L 0 {shape_data['height']} Z"
                print(f"Shape {shape_id}: Using default rectangle (no master geometry)")
            else:
                svg_path = master['path']
                print(f"Shape {shape_id}: Using master geometry from {shape_data['master_id']}")

            # Calculate position. Visio's PinX/PinY is the center of the shape.
            # SVG's x/y is the top-left corner.
            x = shape_data['pin_x'] - (shape_data['width'] / 2)
            y = self.page_height - (shape_data['pin_y'] + (shape_data['height'] / 2)) # Invert Y

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

            svg_elements.append(f'  <path d="{svg_path}" transform="{path_transform}" style="fill:white;stroke:black;stroke-width:2;" />')

            if shape_data['text']:
                # Center text within the shape
                text_x = shape_data['width'] / 2
                text_y = shape_data['height'] / 2
                svg_elements.append(f'  <text x="{text_x}" y="{text_y}" dominant-baseline="middle" text-anchor="middle" font-family="Arial" font-size="12">{shape_data["text"]}</text>')
            
            svg_elements.append('</g>')

        # Process connectors
        for conn_id, conn_data in self.connectors.items():
            from_shape = self.shapes.get(conn_data['from_sheet'])
            to_shape = self.shapes.get(conn_data['to_sheet'])

            if from_shape and to_shape:
                x1 = from_shape['pin_x']
                y1 = self.page_height - from_shape['pin_y']
                x2 = to_shape['pin_x']
                y2 = self.page_height - to_shape['pin_y']
                svg_elements.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" style="stroke:black;stroke-width:2;" />')

        return "\n".join(svg_elements)


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
                
                self._parse_masters(zf)
                
                # Check for failure in parsing page shapes before continuing
                if not self._parse_page_shapes():
                    return None # Stop conversion if page parsing fails
                
                svg_content = self._generate_svg_content()
                
                # Assemble the final SVG file
                svg_output = f'<svg width="{self.page_width}" height="{self.page_height}" xmlns="http://www.w3.org/2000/svg">\n'
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
