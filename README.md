# VSDX to SVG Converter

## Features

### Coordinate Normalization
- Automatically scales and centers diagram to fit standard A4 landscape page
- Preserves relative positioning of shapes
- Handles diagrams of varying sizes and scales

### Advanced Styling Support
- Parses color definitions from Visio's `document.xml`
- Supports style inheritance and themed values
- Extracts line, fill, and text styling information
- Handles color references and complex style hierarchies

## Styling Details

The converter now supports comprehensive style parsing:
- Color Extraction: Reads RGB color definitions from `document.xml`
- Style Inheritance: Follows Visio's style inheritance mechanism
- Supports multiple style types:
  * Line Styles
  * Fill Styles
  * Text Styles

### Style Resolution Process
1. Check direct style properties
2. If property is inherited or themed, look for parent style
3. Fallback to default values if no specific style is found

## Coordinate Transformation

The converter uses a sophisticated coordinate normalization technique:
- Calculates total diagram bounding box
- Scales diagram to fit standard A4 landscape
- Maintains aspect ratio
- Centers diagram on the page

## Limitations
- Some complex Visio-specific styling might not be perfectly replicated
- Gradient and advanced effects may not be fully supported

## Future Improvements
- Enhanced gradient and effect parsing
- More precise style inheritance
- Support for more complex Visio styling features
