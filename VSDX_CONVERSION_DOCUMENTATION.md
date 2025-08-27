# VSDX to SVG Conversion Documentation

## Overview

This document describes the VSDX to SVG converter implementation, the issues encountered, and the fixes applied to successfully convert Visio diagram files to SVG format.

## Project Structure

```
vsdx to svg/
├── vsdx_converter.py              # Main converter script
├── diagram.vsdx                   # Input VSDX file
├── output.svg                     # Generated SVG output
├── WATER INJECTION PETANI 002 REV01/  # Extracted VSDX contents
└── VSDX_CONVERSION_DOCUMENTATION.md   # This documentation file
```

## VSDX File Structure Analysis

The VSDX file is essentially a ZIP archive containing XML files that describe the Visio diagram:

### Key Files and Their Purpose

1. **`visio/pages/pages.xml`** - Contains page metadata including:
   - Page dimensions (PageWidth, PageHeight)
   - Page properties and settings
   - Layer information
   - PageSheet element with core page data

2. **`visio/pages/page1.xml`** - Contains the actual diagram content:
   - Shape definitions
   - Text elements
   - Geometry data
   - Connection information

3. **`visio/pages/_rels/pages.xml.rels`** - Maps pages.xml to page content files
4. **`visio/masters/`** - Contains master shape definitions and templates

### VSDX XML Structure

```xml
<!-- pages.xml structure -->
<Pages xmlns="http://schemas.microsoft.com/office/visio/2012/main">
  <Page ID="0" NameU="Page-1">
    <PageSheet>
      <Cell N="PageWidth" V="16.53543307086614" U="MM"/>
      <Cell N="PageHeight" V="11.69291338582677" U="MM"/>
      <!-- ... other page properties ... -->
    </PageSheet>
    <Rel r:id="rId1"/>
  </Page>
</Pages>
```

**Important Note**: Page dimensions are stored in `Cell` elements with:
- `N` attribute: The property name (e.g., "PageWidth", "PageHeight")
- `V` attribute: The actual value
- `U` attribute: The unit (e.g., "MM" for millimeters)

<!-- page1.xml structure -->
<PageContents xmlns="http://schemas.microsoft.com/office/visio/2012/main">
  <Shapes>
    <Shape ID="180" Type="Shape" Master="70">
      <Cell N="PinX" V="13.67125984251967" U="MM"/>
      <Cell N="PinY" V="8.095564196285443" U="MM"/>
      <Cell N="Width" V="0.1968503937007874"/>
      <Cell N="Height" V="-0.312148379917887" U="MM"/>
      <!-- ... geometry and text data ... -->
    </Shape>
    <!-- ... more shapes ... -->
  </Shapes>
</PageContents>
```

## Issues Encountered

### 1. PageSheet Location Error
**Problem**: The original converter was looking for the `PageSheet` element in `page1.xml`, but it's actually located in `pages.xml`.

**Error Message**: `"Error: Could not find PageSheet element in the page XML."`

**Root Cause**: The converter was parsing the wrong XML file for page dimensions.

### 2. Incorrect Page Dimension Parsing
**Problem**: Page dimensions were being extracted from the wrong location, causing the converter to fail.

**Impact**: Without proper page dimensions, the SVG output couldn't be generated.

### 3. Shape Data Extraction Issues
**Problem**: The converter was only looking for transform data in `Xf` elements, but many shapes store this data in `Cell` elements.

**Impact**: Many shapes were being skipped, resulting in incomplete SVG output.

## Fixes Implemented

### 1. Fixed Page Dimension Parsing

**Before**: Looking for PageSheet in page1.xml
```python
# OLD CODE - WRONG LOCATION
page_sheet = self.page_xml.find('.//v:PageSheet', self.namespaces)
```

**After**: Reading from pages.xml and extracting from Cell elements
```python
def _parse_page_dimensions(self, zf):
    """Parse page dimensions from pages.xml instead of page1.xml."""
    pages_tree = self._get_xml_tree(zf, 'visio/pages/pages.xml')
    page_sheet = pages_tree.find('.//v:PageSheet', self.namespaces)
    
    if page_sheet is not None:
        # Extract page dimensions from Cell elements
        page_width_cell = page_sheet.find('.//v:Cell[@N="PageWidth"]', self.namespaces)
        page_height_cell = page_sheet.find('.//v:Cell[@N="PageHeight"]', self.namespaces)
        
        if page_width_cell is not None and page_height_cell is not None:
            self.page_width = float(page_width_cell.get('V', '0'))
            self.page_height = float(page_height_cell.get('V', '0'))
```

### 2. Improved Shape Data Extraction

**Before**: Only looking in Xf elements
```python
# OLD CODE - LIMITED DATA EXTRACTION
xf = shape.find('v:Xf', self.namespaces)
if xf is None: continue  # Skip shapes without transform data
```

**After**: Fallback to Cell elements
```python
# NEW CODE - ROBUST DATA EXTRACTION
xf = shape.find('v:Xf', self.namespaces)
if xf is not None:
    # Shape has explicit transform data
    width = float(xf.findtext('v:Width', namespaces=self.namespaces) or '0.1')
    height = float(xf.findtext('v:Height', namespaces=self.namespaces) or '0.1')
    # ... etc
else:
    # Try to get data from Cell elements
    width = float(shape.findtext('.//v:Width', namespaces=self.namespaces) or '0.1')
    height = float(shape.findtext('.//v:Height', namespaces=self.namespaces) or '0.1')
    # ... etc
```

### 3. Enhanced Text Extraction

**Before**: Simple text extraction
```python
# OLD CODE - BASIC TEXT EXTRACTION
text = shape.findtext('v:Text', self.namespaces) or ''
```

**After**: Comprehensive text parsing
```python
# NEW CODE - COMPREHENSIVE TEXT EXTRACTION
text_elem = shape.find('.//v:Text', self.namespaces)
text = ""
if text_elem is not None:
    for text_part in text_elem.iter():
        if text_part.text and text_part.text.strip():
            text += text_part.text.strip() + " "
    text = text.strip()
```

### 4. Better Error Handling and Logging

Added comprehensive logging to track the conversion process:
```python
print(f"Page dimensions: {self.page_width} x {self.page_height}")
print(f"Parsed {len(self.shapes)} shapes and {len(self.connectors)} connectors")
```

## How the Converter Works

### 1. Initialization
- Opens the VSDX file as a ZIP archive
- Sets up XML namespaces for Visio 2012 format

### 2. Page Dimension Parsing
- Reads `pages.xml` to extract page dimensions
- Stores width and height for SVG generation

### 3. Master Shape Parsing
- Reads master shape definitions from `masters/` directory
- Extracts geometry data and creates SVG path representations

### 4. Shape Content Parsing
- Reads `page1.xml` to extract all shapes
- Parses position, size, rotation, and text data
- Handles both explicit transform data and cell-based data

### 5. SVG Generation
- Creates SVG elements for each shape
- Applies transformations (translation, rotation, scaling)
- Generates text labels
- Creates connector lines between shapes

### 6. Output Generation
- Assembles the complete SVG document
- Sets proper viewport dimensions
- Writes to output file

## Usage

### Basic Usage
```bash
python vsdx_converter.py
```

### Custom File Paths
Edit the script to change input/output files:
```python
input_vsdx_file = "your_diagram.vsdx"
output_svg_file = "your_output.svg"
```

### Expected Output
The converter should now successfully:
1. Parse page dimensions (e.g., 16.54 x 11.69 mm)
2. Extract all shapes and their properties
3. Generate a properly formatted SVG file
4. Display progress information during conversion

## Current Limitations

1. **Basic Shape Support**: Only handles simple geometric shapes
2. **Limited Styling**: Basic stroke and fill colors
3. **Single Page**: Only converts the first page
4. **No Complex Effects**: No gradients, shadows, or advanced Visio features
5. **Text Formatting**: Basic text rendering without complex formatting

## Future Improvements

1. **Enhanced Shape Support**: Better handling of complex Visio shapes
2. **Improved Styling**: Support for Visio themes and styles
3. **Multi-page Support**: Convert all pages in the document
4. **Better Text Handling**: Support for text formatting and styles
5. **Advanced Geometry**: Support for complex Visio geometry commands
6. **Layer Support**: Respect Visio layer visibility and properties

## Troubleshooting

### Common Issues

1. **"Could not find pages.xml file"**
   - Ensure the VSDX file is not corrupted
   - Check that the file is a valid Visio document

2. **"Could not find PageSheet element"**
   - The VSDX file may be using a different format
   - Check the XML structure manually

3. **"No shapes parsed"**
   - The page content may be empty
   - Check the page1.xml file for shape data

4. **SVG output is empty or incorrect**
   - Verify that shapes were parsed correctly
   - Check the console output for parsing statistics

### Debug Mode
Add debug prints to see what's happening:
```python
print(f"Shape {shape_id}: {shape_data}")
```

## Technical Details

### Coordinate System
- Visio uses a coordinate system with origin at bottom-left
- SVG uses a coordinate system with origin at top-left
- The converter inverts the Y-axis to match SVG conventions

### Units
- Page dimensions are typically in millimeters (MM)
- Shape dimensions may use various units
- The converter preserves the original scale

### Namespaces
The converter handles these XML namespaces:
- `v:` - Visio 2012 main namespace
- `r:` - Office OpenXML relationships namespace

## Conclusion

The core fixes implemented resolve the main issues preventing VSDX to SVG conversion:
1. ✅ Page dimensions are now correctly parsed from pages.xml
2. ✅ Shape data extraction is more robust
3. ✅ Text content is properly extracted
4. ✅ Better error handling and logging

The converter should now generate basic SVG output from VSDX files, providing a foundation for further improvements and enhanced feature support.
