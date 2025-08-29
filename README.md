# VSDX to SVG Exploration Repository

This repository explores various approaches for converting Microsoft Visio (.vsdx) files to Scalable Vector Graphics (.svg) format.

## Overview

Converting Visio diagrams to SVG involves parsing complex XML structures, handling various Visio-specific features, and translating them to web-compatible SVG format. This repository serves as a research and development space for different conversion methodologies.

## Current Approaches

Different conversion approaches are implemented in separate branches of this repository:

**Dama Branch:** [`dama`](https://github.com/RunningPie/VSDX_TO_SVG/tree/dama)

**Faris Branch:** [`faris`](https://github.com/RunningPie/VSDX_TO_SVG/tree/faris)

**Micky Branch:** [`micky`](https://github.com/RunningPie/VSDX_TO_SVG/tree/Micky)

## Repository Structure

```
vsdx_converter.py          # Main conversion script
converter_implementation_docs.md  # Detailed implementation notes
diagram.vsdx              # Sample Visio file for testing
output.svg                # Example conversion output
WATER INJECTION PETANI... # Test data directory
```

## Goals

- Research effective methods for VSDX to SVG conversion
- Document different approaches and their trade-offs
- Provide working examples for various conversion techniques
- Explore optimization opportunities for different use cases
