# IFC Viewer and Editor

## Description
The IFC Viewer and Editor is a powerful tool for viewing, analyzing, and editing Industry Foundation Classes (IFC) files. It provides both a command-line interface (CLI) and a web-based interface using Streamlit, allowing users to interact with IFC files in various ways.

## Features
- Select and view IFC elements
- Display detailed properties of selected elements
- Show layer information for applicable elements
- Update existing properties or add new properties to elements
- Count elements by type
- List all element types in the IFC file
- Export element properties and layer information to CSV files

## Installation

### Prerequisites
- Python 3.7+
- pip

### Steps
1. Clone the repository:
   ```
   git clone https://github.com/apollosbangalu/ifc-viewer-editor.git
   cd ifc-viewer-editor
   ```

2. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

## Usage

### Command-Line Interface
To use the command-line interface:

```
python command_line_ifc_viewer_editor.py
```

Follow the on-screen prompts to interact with your IFC file.

### Web Interface
To use the web-based interface:

```
streamlit run streamlit_ifc_viewer_editor.py
```

This will launch the Streamlit app in your default web browser.

## User Guide

### Selecting Elements
- Use the 'Select' command to choose specific elements from the IFC file.
- You can select by element type, ID, or choose from a list of all types.

### Viewing Elements
- After selecting elements, use the 'View' command to see basic information about them.

### Displaying Properties
- Use the 'Properties' command to show detailed properties of selected elements.

### Working with Layers
- For elements with layers (e.g., walls, slabs), use the 'Layers' command to view layer information.

### Updating Properties
- Select an element, then use the 'Update' command to modify existing properties or add new ones.

### Saving Changes
- Use the 'Save' command to permanently apply any modifications to the IFC file.

### Counting Elements
- The 'Count' command allows you to count the number of elements of a specific type.

### Listing Element Types
- Use the 'List' command to see all element types present in the IFC file.

### Exporting Data
- The 'Export' command allows you to export properties or layer information to CSV files.

## Contributing
Contributions to the IFC Viewer and Editor are welcome! Please feel free to submit pull requests or open issues for any bugs or feature requests.

## License
[Specify your license here]

## Contact
[Your contact information or project maintainer's contact]
