# VSDX to SVG Converter

Converts Microsoft Visio diagrams (.vsdx files) into scalable SVG format while preserving visual appearance.

## What This Tool Does

Converts Visio diagrams to SVG files that can be:
- Used on websites and in web applications
- Edited with SVG editors
- Scaled without quality loss
- Shared with universal compatibility

## Quick Start

### Basic Usage
```bash
python vsdx_converter.py
```

### Advanced Usage
```python
from vsdx_converter import VsdxToSvgConverter

# Convert a single file
converter = VsdxToSvgConverter("your_diagram.vsdx")
svg_content = converter.convert()

# Save to file
with open("output.svg", "w", encoding="utf-8") as f:
    f.write(svg_content)
```

## Requirements

- Python 3.6+
- No external dependencies - Uses only Python's built-in libraries
- Microsoft Visio .vsdx files (Visio 2013+ format)

## Features

### Visual Fidelity
- Preserves visual styling (colors, fonts, line styles)
- Maintains layout and positioning
- Text formatting and positioning
- Shape effects (shadows, bevels, blur)

### Scaling
- Automatic sizing to standard page sizes
- Aspect ratio preservation
- Fits diagrams to standard formats

### Technical Features
- Theme support for Visio themes and color schemes
- Style inheritance for complex styling hierarchies
- Master shapes (custom and built-in)
- Clean, standards-compliant SVG output

## Conversion Process

![VSDX to SVG Conversion Process](https://raw.githubusercontent.com/RunningPie/VSDX_TO_SVG/dama/Flowchart%20VSDX%20to%20SVG.png)

## Use Cases

- Web developers embedding diagrams in websites and applications
- Technical writers creating documentation with scalable diagrams
- Presenters using diagrams in slide presentations
- Designers editing Visio diagrams in SVG editors
- Anyone needing to share Visio diagrams digitally

## Output

After conversion, you get:
- Clean SVG file ready for use
- Preserved text and annotations
- Optimized file sizes
- Cross-platform compatibility

## Troubleshooting

### Common Issues

**File not found error**
- Verify the .vsdx file path is correct
- Check file permissions

**Empty or incomplete output**
- Ensure the Visio file is not corrupted
- Try with a simpler diagram first

**Styling issues**
- Complex themes may need manual adjustment in SVG editors
- Some advanced Visio effects may not convert perfectly
