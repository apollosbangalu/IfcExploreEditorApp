import streamlit as st
import os
import csv
import re
import ifcopenshell
from ifcopenshell.util import element, placement
import tempfile
import base64

class IFCViewerEditor:
    def __init__(self, ifc_file_path):
        self.ifc_file_path = ifc_file_path
        self.ifc_file = ifcopenshell.open(ifc_file_path)

    def find_close_matches(self, identifier):
        all_types = set(element.is_a() for element in self.ifc_file)
        return sorted([t for t in all_types if identifier.lower() in t.lower()])

    def select_elements(self, identifier):
        try:
            if identifier.isdigit():
                element = self.ifc_file.by_id(int(identifier))
                if element is None:
                    return [], f"No element found with ID {identifier}"
                return [element], None
            else:
                close_matches = self.find_close_matches(identifier)
                if not close_matches:
                    return [], f"No elements found matching '{identifier}'"
                return close_matches, None
        except Exception as e:
            return [], f"Error selecting elements: {e}"


    def get_elements_by_type(self, element_type):
        return self.ifc_file.by_type(element_type)
    

    def create_new_property(self, element, property_name, property_value):
        try:
            # Create a new IfcPropertySingleValue
            property_value = ifcopenshell.api.run("property.add_property", self.ifc_file,
                property_set=None, name=property_name, value=property_value)
            
            # Create a new IfcPropertySet if it doesn't exist
            property_set = ifcopenshell.api.run("property.add_pset", self.ifc_file,
                product=element, name=f"Custom_Properties_{element.is_a()}")
            
            # Add the property to the property set
            ifcopenshell.api.run("property.edit_property", self.ifc_file,
                property=property_value, attributes={"Name": property_name})
            
            # Assign the property set to the element
            ifcopenshell.api.run("property.assign_pset", self.ifc_file,
                product=element, pset=property_set)
            
            return True
        except Exception as e:
            print(f"Error creating new property: {e}")
            return False    
###################################################################################################3
    def get_element_properties(self, element):
        if element is None:
            return {}
        properties = {
            "Name": element.Name,
            "Type": element.is_a(),
            "GlobalId": element.GlobalId
        }
        
        # Check if the element has layers
        if hasattr(element, 'HasAssociations'):
            for association in element.HasAssociations:
                if association.is_a('IfcRelAssociatesMaterial'):
                    relating_material = association.RelatingMaterial
                    if relating_material.is_a('IfcMaterialLayerSetUsage'):
                        properties['HasLayers'] = True
                        properties['LayerSetName'] = relating_material.ForLayerSet.LayerSetName
                        properties['NumberOfLayers'] = len(relating_material.ForLayerSet.MaterialLayers)
        
        # Get all property sets
        psets = ifcopenshell.util.element.get_psets(element)
        for pset_name, pset_data in psets.items():
            for prop_name, prop_value in pset_data.items():
                properties[f"{pset_name}.{prop_name}"] = prop_value

        # Get quantity information
        quantities = ifcopenshell.util.element.get_psets(element, qtos_only=True)
        for qto_name, qto_data in quantities.items():
            for quantity_name, quantity_value in qto_data.items():
                properties[f"{qto_name}.{quantity_name}"] = quantity_value

        # Add material information
        materials = ifcopenshell.util.element.get_materials(element)
        if materials:
            if isinstance(materials, list):
                properties['Materials'] = [m.Name for m in materials]
            elif isinstance(materials, ifcopenshell.entity_instance):
                if materials.is_a('IfcMaterial'):
                    properties['Material'] = materials.Name
                elif materials.is_a('IfcMaterialLayerSet'):
                    properties['MaterialLayers'] = []
                    for i, layer in enumerate(materials.MaterialLayers, 1):
                        layer_info = {
                            'Position': i,
                            'Material': layer.Material.Name if layer.Material else 'Unknown',
                            'Thickness': layer.LayerThickness,
                            'IsVentilated': layer.IsVentilated if hasattr(layer, 'IsVentilated') else 'N/A'
                        }
                        
                        # Calculate area and volume if possible
                        if element.is_a('IfcWall') or element.is_a('IfcSlab'):
                            quantity_set = ifcopenshell.util.element.get_psets(element, qtos_only=True)
                            if 'Qto_WallBaseQuantities' in quantity_set:
                                area = quantity_set['Qto_WallBaseQuantities'].get('GrossFootprintArea', 0)
                                layer_info['Area'] = area
                                layer_info['Volume'] = area * layer.LayerThickness
                            elif 'Qto_SlabBaseQuantities' in quantity_set:
                                area = quantity_set['Qto_SlabBaseQuantities'].get('GrossArea', 0)
                                layer_info['Area'] = area
                                layer_info['Volume'] = area * layer.LayerThickness
                        
                        properties['MaterialLayers'].append(layer_info)
                elif materials.is_a('IfcMaterialList'):
                    properties['MaterialList'] = [m.Name for m in materials.Materials]
                elif materials.is_a('IfcMaterialLayerSetUsage'):
                    properties['MaterialLayerSetUsage'] = {
                        'LayerSet': materials.ForLayerSet.LayerSetName,
                        'LayerSetDirection': materials.LayerSetDirection,
                        'DirectionSense': materials.DirectionSense,
                        'OffsetFromReferenceLine': materials.OffsetFromReferenceLine
                    }

        # Add placement information
        if element.is_a('IfcProduct'):
            matrix = ifcopenshell.util.placement.get_local_placement(element.ObjectPlacement)
            properties['LocalPlacement'] = matrix.tolist()

        return properties

    def update_element_property(self, elements, property_name, new_value):
        if not elements:
            return False
        success = False
        for element in elements:
            if property_name == "Name":
                element.Name = new_value
                success = True
            else:
                for definition in element.IsDefinedBy:
                    if definition.is_a('IfcRelDefinesByProperties'):
                        property_set = definition.RelatingPropertyDefinition
                        for property in property_set.HasProperties:
                            if property.Name == property_name:
                                if hasattr(property, 'NominalValue'):
                                    property.NominalValue.wrappedValue = new_value
                                    success = True
                                elif hasattr(property, 'Value'):
                                    property.Value = new_value
                                    success = True
        return success

    def save_ifc_file(self):
        try:
            backup_path = self.ifc_file_path + '.bak'
            self.ifc_file.write(backup_path)
            st.success(f"Backup created: {backup_path}")
            self.ifc_file.write(self.ifc_file_path)
            st.success("Changes saved successfully.")
            return True
        except Exception as e:
            st.error(f"Error saving file: {e}")
            return False

    def count_elements_by_type(self, element_type):
        return len(self.ifc_file.by_type(element_type))

    def list_all_element_types(self):
        return sorted(set(element.is_a() for element in self.ifc_file))

    def get_layer_properties(self, layer):
        properties = {
            "Material": layer.Material.Name if layer.Material else "Unknown",
            "Thickness": layer.LayerThickness,
        }
        
        # Check if IsVentilated attribute exists (IFC4)
        if hasattr(layer, 'IsVentilated'):
            properties["IsVentilated"] = layer.IsVentilated
        
        # Check if Priority attribute exists (IFC4)
        if hasattr(layer, 'Priority'):
            properties["Priority"] = layer.Priority
        
        # Add material properties if available
        if layer.Material:
            material = layer.Material
            properties["MaterialCategory"] = material.Category if hasattr(material, "Category") else "N/A"
            properties["MaterialDescription"] = material.Description if hasattr(material, "Description") else "N/A"
            
            # Add material properties from property sets
            material_psets = ifcopenshell.util.element.get_psets(material)
            for pset_name, pset_props in material_psets.items():
                for prop_name, prop_value in pset_props.items():
                    properties[f"Material.{pset_name}.{prop_name}"] = prop_value

        return properties

    def select_layer(self, layer_index, element):
        if element is None:
            st.warning("No element provided.")
            return None
        
        if hasattr(element, 'HasAssociations'):
            for association in element.HasAssociations:
                if association.is_a('IfcRelAssociatesMaterial'):
                    relating_material = association.RelatingMaterial
                    if relating_material.is_a('IfcMaterialLayerSetUsage'):
                        layers = relating_material.ForLayerSet.MaterialLayers
                        if 0 <= layer_index < len(layers):
                            self.selected_layer = layers[layer_index]
                            return self.selected_layer
        
        st.warning("No layer found at the specified index.")
        return None

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename).replace(" ", "_")

def export_to_csv(filename, data):
    if isinstance(data, dict):
        data = [data]
    if not data:
        st.warning(f"No data to export to {filename}")
        return None
    
    with tempfile.NamedTemporaryFile(mode='w+', newline='', delete=False, suffix='.csv') as temp_file:
        fieldnames = list(data[0].keys())
        writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow(row)
    
    with open(temp_file.name, 'rb') as f:
        csv_contents = f.read()
    
    os.unlink(temp_file.name)
    return csv_contents
###########################################################################################################

def show_user_guide():
    st.markdown("""
    # IFC Viewer and Editor User Guide

    ## Introduction
    The IFC Viewer and Editor is a Streamlit-based web application designed to view, analyze, and edit Industry Foundation Classes (IFC) files. This tool allows users to explore IFC elements, view their properties, update existing properties, and even add new properties to elements.

    ## Getting Started
    1. Launch the application using Streamlit.
    2. Upload your IFC file using the file uploader on the main page.
    3. Once uploaded, you'll see a sidebar with various commands to interact with the IFC file.

    ## Main Features

    ### 1. Select
    - **Purpose**: Choose specific elements from the IFC file for viewing or editing.
    - **How to use**:
      - Enter an element type, ID, or 'list' to see all types.
      - Follow the prompts to narrow down your selection.
      - You can select single or multiple elements.

    ### 2. View
    - **Purpose**: Display basic information about selected elements.
    - **How to use**:
      - First, use the 'Select' command to choose elements.
      - Then, use 'View' to see details like ID, Type, Name, and GlobalId.

    ### 3. Properties
    - **Purpose**: Show detailed properties of selected elements.
    - **How to use**:
      - Select elements first, then use this command to see all properties in JSON format.

    ### 4. Layers
    - **Purpose**: Display layer information for elements that have layers (e.g., walls, slabs).
    - **How to use**:
      - Select elements, then use this command to view layer details if available.

    ### 5. Update
    - **Purpose**: Modify existing properties or add new properties to selected elements.
    - **How to use**:
      - Select an element to update.
      - Choose a property from the dropdown or select "Create new property".
      - For existing properties:
        - View the current value.
        - Enter a new value and click "Update Property".
      - For new properties:
        - Enter the new property name and value.
        - Click "Create Property".
      - Use "Save Changes" to permanently apply the updates to the IFC file.

    ### 6. Save
    - **Purpose**: Save all changes made to the IFC file.
    - **How to use**:
      - Click this command and confirm to save all modifications to the file.

    ### 7. Count
    - **Purpose**: Count the number of elements of a specific type in the IFC file.
    - **How to use**:
      - Select an element type from the dropdown.
      - Click "Count Elements" to see the total number.

    ### 8. List
    - **Purpose**: Display all element types present in the IFC file.
    - **How to use**:
      - Simply click this command to see a list of all element types.

    ### 9. Export
    - **Purpose**: Export properties or layer information of selected elements to CSV files.
    - **How to use**:
      - Choose to export Properties, Layers, or Both.
      - Select between Separate or Collective export modes.
      - Click "Export" and use the download buttons to save the CSV files.

    ## Tips
    - Always select elements before trying to view, update, or export their information.
    - Use the "Reset" button in the sidebar to start over with a new file or clear your selections.
    - Remember to save your changes using the "Save" command before exporting or closing the application.
    - When updating properties, double-check the current value before making changes to avoid unintended modifications.

    ## Troubleshooting
    - If you encounter any issues, try resetting the application and re-uploading your IFC file.
    - Ensure your IFC file is valid and not corrupted before uploading.
    - For large IFC files, some operations may take longer to process. Please be patient.

    We hope this IFC Viewer and Editor helps you efficiently analyze and modify your IFC files. For any further assistance or feature requests, please contact the development team.
    """)



def main():
    st.set_page_config(page_title="IFC Viewer and Editor", layout="wide")
    st.title("IFC Viewer and Editor")

    if 'viewer_editor' not in st.session_state:
        uploaded_file = st.file_uploader("Choose an IFC file", type="ifc")
        if uploaded_file is not None:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.ifc') as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_file_path = tmp_file.name
            st.session_state.viewer_editor = IFCViewerEditor(tmp_file_path)
            st.session_state.selected_elements = []
            st.rerun()
    else:
        st.sidebar.header("Commands")
        command = st.sidebar.selectbox(
            "Select a command",
            ["User Guide", "Select", "View", "Properties", "Layers", "Update", "Save", "Count", "List", "Export"]
        )

        if command == "User Guide":
            show_user_guide()
        elif command == "Select":
            select_elements()
        elif command == "View":
            view_elements()
        elif command == "Properties":
            show_properties()
        elif command == "Layers":
            show_layers()
        elif command == "Update":
            update_property()
        elif command == "Save":
            save_changes()
        elif command == "Count":
            count_elements()
        elif command == "List":
            list_element_types()
        elif command == "Export":
            export_data()

        if st.sidebar.button("Reset"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

def select_elements():
    st.session_state.step = st.session_state.get('step', 0)
    
    if st.session_state.step == 0:
        identifier = st.text_input("Enter element type, ID, or 'list' to see all types:")
        if st.button("Next"):
            if identifier.lower() == 'list':
                st.session_state.element_types = st.session_state.viewer_editor.list_all_element_types()
                st.session_state.step = 1
            else:
                st.session_state.results, error = st.session_state.viewer_editor.select_elements(identifier)
                if error:
                    st.error(error)
                else:
                    st.session_state.step = 2

    elif st.session_state.step == 1:
        st.write("All element types in the IFC file:")
        for i, element_type in enumerate(st.session_state.element_types, 1):
            st.write(f"  {i}. {element_type}")
        type_choice = st.text_input("Enter the number or name of the type to select:")
        if st.button("Next"):
            if type_choice.isdigit() and 1 <= int(type_choice) <= len(st.session_state.element_types):
                identifier = st.session_state.element_types[int(type_choice) - 1]
            else:
                identifier = type_choice
            st.session_state.results, error = st.session_state.viewer_editor.select_elements(identifier)
            if error:
                st.error(error)
            else:
                st.session_state.step = 2

    elif st.session_state.step == 2:
        if len(st.session_state.results) == 1 and isinstance(st.session_state.results[0], ifcopenshell.entity_instance):
            st.session_state.selected_elements = st.session_state.results
            st.session_state.selected_element_ids = [elem.id() for elem in st.session_state.selected_elements]  # Store element IDs
            st.success(f"Selected element: ID {st.session_state.results[0].id()}, Type: {st.session_state.results[0].is_a()}, Name: {st.session_state.results[0].Name}")
            st.session_state.step = 0
        else:
            st.write(f"Found {len(st.session_state.results)} possible matches:")
            for i, match in enumerate(st.session_state.results, 1):
                st.write(f"{i}. {match}")
            element_choice = st.text_input("Enter the number of the type to select:")
            if st.button("Next"):
                if element_choice.isdigit() and 1 <= int(element_choice) <= len(st.session_state.results):
                    st.session_state.elements = st.session_state.viewer_editor.get_elements_by_type(st.session_state.results[int(element_choice) - 1])
                    st.session_state.step = 3
                else:
                    st.error("Invalid selection. Please try again.")

    elif st.session_state.step == 3:
        st.write(f"Found {len(st.session_state.elements)} elements of type {st.session_state.elements[0].is_a()}:")
        for i, elem in enumerate(st.session_state.elements, 1):
            st.write(f"{i}. ID: {elem.id()}, Name: {elem.Name}")
        
        multi_select = st.checkbox("Select multiple elements?")
        if multi_select:
            selected_indices = st.multiselect("Select elements by index:", range(1, len(st.session_state.elements) + 1))
        else:
            selected_indices = [st.number_input("Enter the number of the element to select:", min_value=1, max_value=len(st.session_state.elements), value=1)]
        
        if st.button("Confirm Selection"):
            st.session_state.selected_elements = [st.session_state.elements[i-1] for i in selected_indices]
            st.session_state.selected_element_ids = [elem.id() for elem in st.session_state.selected_elements]  # Store element IDs
            st.success(f"Selected {len(st.session_state.selected_elements)} elements")
            for element in st.session_state.selected_elements:
                st.write(f"ID {element.id()}, Type: {element.is_a()}, Name: {element.Name}")
            st.session_state.step = 0





def view_elements():
    if st.session_state.selected_elements:
        for i, element in enumerate(st.session_state.selected_elements, 1):
            st.subheader(f"Element {i}")
            st.write(f"ID: {element.id()}")
            st.write(f"Type: {element.is_a()}")
            st.write(f"Name: {element.Name}")
            st.write(f"GlobalId: {element.GlobalId}")
    else:
        st.warning("No elements selected. Use 'Select' command first.")

def show_properties():
    if st.session_state.selected_elements:
        for element in st.session_state.selected_elements:
            st.subheader(f"{element.is_a()} (ID: {element.id()})")
            properties = st.session_state.viewer_editor.get_element_properties(element)
            st.json(properties)
    else:
        st.warning("No elements selected. Use 'Select' command first.")

def show_layers():
    if st.session_state.selected_elements:
        for element in st.session_state.selected_elements:
            properties = st.session_state.viewer_editor.get_element_properties(element)
            if 'HasLayers' in properties and properties['HasLayers']:
                st.subheader(f"Layers for {element.is_a()} (ID: {element.id()})")
                for i in range(properties['NumberOfLayers']):
                    layer = st.session_state.viewer_editor.select_layer(i, element)
                    if layer:
                        st.write(f"Layer {i+1}")
                        layer_props = st.session_state.viewer_editor.get_layer_properties(layer)
                        st.json(layer_props)
            else:
                st.warning(f"Element {element.id()} does not have layers.")
    else:
        st.warning("No elements selected. Use 'Select' command first.")


def update_property():
    if 'selected_element_ids' in st.session_state and st.session_state.selected_element_ids:
        # Retrieve elements by their IDs
        elements = [st.session_state.viewer_editor.ifc_file.by_id(id) for id in st.session_state.selected_element_ids]
        element_options = [f"{elem.is_a()} (ID: {elem.id()})" for elem in elements]
        selected_option = st.selectbox("Select element to update", element_options)
        
        if selected_option:
            element_id = int(selected_option.split("(ID: ")[1].rstrip(")"))
            element = st.session_state.viewer_editor.ifc_file.by_id(element_id)
            
            # Get all properties of the selected element
            properties = st.session_state.viewer_editor.get_element_properties(element)
            
            # Create a list of property names
            property_names = list(properties.keys())
            property_names.insert(0, "Create new property")  # Add option to create new property
            
            selected_property = st.selectbox("Select property to update", property_names)
            
            if selected_property == "Create new property":
                new_property_name = st.text_input("Enter new property name")
                new_property_value = st.text_input("Enter new property value")
                if st.button("Create Property"):
                    # Logic to create a new property
                    success = st.session_state.viewer_editor.create_new_property(element, new_property_name, new_property_value)
                    if success:
                        st.success(f"Created new property {new_property_name} with value {new_property_value}")
                    else:
                        st.error("Failed to create new property")
            else:
                current_value = properties[selected_property]
                st.write(f"Current value: {current_value}")
                
                new_value = st.text_input("Enter new value", value=str(current_value))
                
                if st.button("Update Property"):
                    if st.session_state.viewer_editor.update_element_property(element, selected_property, new_value):
                        st.success(f"Updated {selected_property} to {new_value} for selected element")
                    else:
                        st.error(f"Failed to update property {selected_property}. Make sure the property exists and is editable.")

            if st.button("Save Changes"):
                if st.session_state.viewer_editor.save_ifc_file():
                    st.success("Changes saved successfully.")
                else:
                    st.error("Failed to save changes.")
    else:
        st.warning("No elements selected. Use 'Select' command first.")




def save_changes():
    if st.button("Save Changes"):
        if st.session_state.viewer_editor.save_ifc_file():
            st.success("Changes saved successfully.")
        else:
            st.error("Failed to save changes.")

def count_elements():
    element_types = st.session_state.viewer_editor.list_all_element_types()
    selected_type = st.selectbox("Select element type to count", element_types)
    if st.button("Count Elements"):
        count = st.session_state.viewer_editor.count_elements_by_type(selected_type)
        st.write(f"Number of {selected_type} elements: {count}")

def list_element_types():
    element_types = st.session_state.viewer_editor.list_all_element_types()
    st.subheader("All element types in the IFC file:")
    for element_type in element_types:
        st.write(f"  {element_type}")

def export_data():
    export_type = st.radio("Export type", ("Properties", "Layers", "Both"))
    export_mode = st.radio("Export mode", ("Separately", "Collectively"))

    if st.button("Export"):
        if not st.session_state.selected_elements:
            st.warning("No elements selected. Use 'Select' command first.")
        else:
            elements_to_export = []
            for element in st.session_state.selected_elements:
                element_data = {
                    'Element Name': element.Name,
                    'Element GlobalId': element.GlobalId,
                    'Element Type': element.is_a(),
                    'Element ID': element.id(),
                    'Properties': st.session_state.viewer_editor.get_element_properties(element),
                    'Layers': []
                }
                if 'HasLayers' in element_data['Properties'] and element_data['Properties']['HasLayers']:
                    for i in range(element_data['Properties']['NumberOfLayers']):
                        layer = st.session_state.viewer_editor.select_layer(i, element)
                        if layer:
                            layer_properties = st.session_state.viewer_editor.get_layer_properties(layer)
                            layer_properties['Layer Number'] = i + 1
                            element_data['Layers'].append(layer_properties)
                elements_to_export.append(element_data)

            elements_to_export.sort(key=lambda x: (x['Element Name'], x['Element GlobalId'], x['Element Type']))

            if export_mode == "Separately":
                for element in elements_to_export:
                    if export_type in ["Properties", "Both"]:
                        csv_data = export_to_csv(f"{sanitize_filename(element['Element Name'])}_{element['Element GlobalId']}_properties.csv", element['Properties'])
                        if csv_data:
                            st.download_button(
                                label=f"Download {element['Element Name']} Properties",
                                data=csv_data,
                                file_name=f"{sanitize_filename(element['Element Name'])}_{element['Element GlobalId']}_properties.csv",
                                mime="text/csv"
                            )
                    if export_type in ["Layers", "Both"] and element['Layers']:
                        csv_data = export_to_csv(f"{sanitize_filename(element['Element Name'])}_{element['Element GlobalId']}_layers.csv", element['Layers'])
                        if csv_data:
                            st.download_button(
                                label=f"Download {element['Element Name']} Layers",
                                data=csv_data,
                                file_name=f"{sanitize_filename(element['Element Name'])}_{element['Element GlobalId']}_layers.csv",
                                mime="text/csv"
                            )
            else:  # Collective export
                if export_type in ["Properties", "Both"]:
                    collective_properties = [{**{'Element Name': e['Element Name'], 'Element GlobalId': e['Element GlobalId'], 'Element Type': e['Element Type']}, **e['Properties']} for e in elements_to_export]
                    csv_data = export_to_csv("collective_properties.csv", collective_properties)
                    if csv_data:
                        st.download_button(
                            label="Download Collective Properties",
                            data=csv_data,
                            file_name="collective_properties.csv",
                            mime="text/csv"
                        )
                if export_type in ["Layers", "Both"]:
                    collective_layers = []
                    for element in elements_to_export:
                        for layer in element['Layers']:
                            collective_layers.append({**{'Element Name': element['Element Name'], 'Element GlobalId': element['Element GlobalId'], 'Element Type': element['Element Type']}, **layer})
                    if collective_layers:
                        csv_data = export_to_csv("collective_layers.csv", collective_layers)
                        if csv_data:
                            st.download_button(
                                label="Download Collective Layers",
                                data=csv_data,
                                file_name="collective_layers.csv",
                                mime="text/csv"
                            )
                    else:
                        st.warning("No layers found for any selected elements")

if __name__ == "__main__":
    main()