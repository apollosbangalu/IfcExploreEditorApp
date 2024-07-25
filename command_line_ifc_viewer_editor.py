import os
import csv
import re
import ifcopenshell
from ifcopenshell.util import element, placement
from tabulate import tabulate

class IFCViewerEditor:
    def __init__(self, ifc_file_path):
        self.ifc_file_path = ifc_file_path
        self.ifc_file = ifcopenshell.open(ifc_file_path)
        self.selected_elements = []
        self.selected_layer = None

    def select_elements(self, identifier):
        try:
            if identifier.isdigit():
                element = self.ifc_file.by_id(int(identifier))
                if element is None:
                    print(f"No element found with ID {identifier}")
                    return []
                self.selected_elements = [element]
                return self.selected_elements
            else:
                close_matches = self.find_close_matches(identifier)
                if not close_matches:
                    print(f"No elements found matching '{identifier}'")
                    return []
                
                if len(close_matches) == 1:
                    print(f"Found 1 possible match: {close_matches[0]}")
                    proceed = input("Do you want to proceed with this match? (y/n): ").lower()
                    if proceed != 'y':
                        return []
                    elements = self.ifc_file.by_type(close_matches[0])
                else:
                    print(f"Found {len(close_matches)} possible matches:")
                    for i, match in enumerate(close_matches, 1):
                        print(f"{i}. {match}")
                    while True:
                        choice = input("Enter the number of the type to select: ")
                        if choice.isdigit() and 1 <= int(choice) <= len(close_matches):
                            elements = self.ifc_file.by_type(close_matches[int(choice) - 1])
                            break
                        else:
                            print("Invalid selection. Please try again.")
                
                print(f"Found {len(elements)} elements of type {elements[0].is_a()}:")
                for i, elem in enumerate(elements, 1):
                    print(f"{i}. ID: {elem.id()}, Name: {elem.Name}")
                
                multiple_select = input("Do you want to select multiple elements? (y/n): ").lower() == 'y'
                selected_elements = []
                
                while True:
                    choice = input("Enter the number, ID, or name of the element to select (or 'done' if finished): ")
                    if choice.lower() == 'done':
                        break
                    if choice.isdigit():
                        if 1 <= int(choice) <= len(elements):
                            selected_elements.append(elements[int(choice) - 1])
                        else:
                            element = self.ifc_file.by_id(int(choice))
                            if element and element in elements:
                                selected_elements.append(element)
                    else:
                        matching_elements = [e for e in elements if e.Name and e.Name.lower() == choice.lower()]
                        if len(matching_elements) == 1:
                            selected_elements.append(matching_elements[0])
                        elif len(matching_elements) > 1:
                            print(f"Multiple elements found with name '{choice}'. Please use the number or ID to select.")
                        else:
                            print("Invalid selection. Please try again.")
                    
                    if selected_elements and not multiple_select:
                        break
                
                self.selected_elements = selected_elements
                return self.selected_elements
        except Exception as e:
            print(f"Error selecting elements: {e}")
            return []

    def find_close_matches(self, identifier):
        all_types = set(element.is_a() for element in self.ifc_file)
        return sorted([t for t in all_types if identifier.lower() in t.lower()])

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
                            'IsVentilated': layer.IsVentilated
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
            print(f"Backup created: {backup_path}")
            self.ifc_file.write(self.ifc_file_path)
            print("Changes saved successfully.")
            return True
        except Exception as e:
            print(f"Error saving file: {e}")
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
            print("No element provided.")
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
        
        print("No layer found at the specified index.")
        return None

def sanitize_filename(filename):
    # Remove invalid characters and replace spaces with underscores
    return re.sub(r'[\\/*?:"<>|]', "", filename).replace(" ", "_")

def confirm_quit():
    confirm = input("Are you sure you want to quit? (y/n): ").lower()
    return confirm == 'y'

def print_help():
    print("\nAvailable commands:")
    print("  help       - Display this help message")
    print("  select     - Select an element by ID, type, or index")
    print("  view       - Display basic information about the selected element")
    print("  properties - Display properties of the selected element")
    print("  layers     - List and select layers of the current element")
    print("  update     - Update a property of the selected element")
    print("  save       - Save changes to the IFC file")
    print("  count      - Count elements of a specific type")
    print("  list       - List all element types in the IFC file")
    print("  export     - Export properties of the selected element or layer to CSV")
    print("  quit       - Exit the program")
    print("\nNote: You can type 'quit' at any time to exit the program.")

def select_helper(viewer_editor):
    while True:
        identifier = input("Enter element type, ID, 'list' to see all types, or 'quit' to exit: ")
        if identifier.lower() == 'quit':
            if confirm_quit():
                return True
            continue
        if identifier.lower() == 'list':
            element_types = viewer_editor.list_all_element_types()
            print("All element types in the IFC file:")
            for i, element_type in enumerate(element_types, 1):
                print(f"  {i}. {element_type}")
            type_choice = input("Enter the number or name of the type to select, or 'quit' to exit: ")
            if type_choice.lower() == 'quit':
                if confirm_quit():
                    return True
                continue
            if type_choice.isdigit() and 1 <= int(type_choice) <= len(element_types):
                identifier = element_types[int(type_choice) - 1]
            else:
                identifier = type_choice
        elements = viewer_editor.select_elements(identifier)
        if elements:
            print("Selected elements:")
            for element in elements:
                print(f"  ID {element.id()}, Type: {element.is_a()}, Name: {element.Name}")
        else:
            print("No elements selected.")
        return False

def view_helper(viewer_editor):
    if viewer_editor.selected_elements:
        for i, element in enumerate(viewer_editor.selected_elements, 1):
            print(f"\nElement {i}:")
            print(f"  ID: {element.id()}")
            print(f"  Type: {element.is_a()}")
            print(f"  Name: {element.Name}")
            print(f"  GlobalId: {element.GlobalId}")
    else:
        print("No elements selected. Use 'select' command first.")

def properties_helper(viewer_editor):
    if viewer_editor.selected_elements:
        all_properties = []
        headers = ["Property"]
        for element in viewer_editor.selected_elements:
            headers.append(f"{element.is_a()} (ID: {element.id()})")
            properties = viewer_editor.get_element_properties(element)
            for key, value in properties.items():
                if not any(prop[0] == key for prop in all_properties):
                    all_properties.append([key] + [""] * len(viewer_editor.selected_elements))
                prop_index = next(i for i, prop in enumerate(all_properties) if prop[0] == key)
                all_properties[prop_index][len(headers) - 1] = str(value)

        print(tabulate(all_properties, headers=headers, tablefmt="grid"))
    else:
        print("No elements selected. Use 'select' command first.")

def layers_helper(viewer_editor):
    if viewer_editor.selected_elements:
        all_layers = []
        headers = ["Property"]
        for element in viewer_editor.selected_elements:
            properties = viewer_editor.get_element_properties(element)
            if 'HasLayers' in properties and properties['HasLayers']:
                headers.append(f"{element.is_a()} (ID: {element.id()})")
                for i in range(properties['NumberOfLayers']):
                    layer = viewer_editor.select_layer(i, element)
                    if layer:
                        layer_props = viewer_editor.get_layer_properties(layer)
                        layer_props['Layer Number'] = i + 1
                        for key, value in layer_props.items():
                            if not any(prop[0] == key for prop in all_layers):
                                all_layers.append([key] + [""] * len(viewer_editor.selected_elements))
                            prop_index = next(i for i, prop in enumerate(all_layers) if prop[0] == key)
                            all_layers[prop_index][len(headers) - 1] = str(value)
            else:
                print(f"Element {element.id()} does not have layers.")

        if all_layers:
            print("\nLayers for selected elements:")
            print(tabulate(all_layers, headers=headers, tablefmt="grid"))

            while True:
                action = input("Enter 'export' to export layer properties, 'back' to return, or 'quit' to exit: ").lower()
                if action == 'export':
                    if export_helper(viewer_editor):
                        return True
                elif action == 'back':
                    break
                elif action == 'quit':
                    if confirm_quit():
                        return True
                else:
                    print("Invalid action. Please try again.")
        else:
            print("No layers found for the selected elements.")
    else:
        print("No elements selected. Use 'select' command first.")
    return False

def count_helper(viewer_editor):
    element_types = viewer_editor.list_all_element_types()
    print("Available element types:")
    for i, element_type in enumerate(element_types, 1):
        print(f"  {i}. {element_type}")
    while True:
        choice = input("Enter the number or name of the type to count (partial matches allowed), or 'quit' to exit: ")
        if choice.lower() == 'quit':
            if confirm_quit():
                return True
            continue
        if choice.isdigit() and 1 <= int(choice) <= len(element_types):
            element_type = element_types[int(choice) - 1]
            count = viewer_editor.count_elements_by_type(element_type)
            print(f"Number of {element_type} elements: {count}")
        else:
            matching_types = [et for et in element_types if choice.lower() in et.lower()]
            if len(matching_types) == 0:
                print(f"No element types found matching '{choice}'")
            elif len(matching_types) == 1:
                element_type = matching_types[0]
                count = viewer_editor.count_elements_by_type(element_type)
                print(f"Number of {element_type} elements: {count}")
            else:
                print(f"Multiple element types found matching '{choice}':")
                for i, et in enumerate(matching_types, 1):
                    count = viewer_editor.count_elements_by_type(et)
                    print(f"  {i}. {et}: {count} elements")
        return False

def export_helper(viewer_editor):
    if not viewer_editor.selected_elements:
        print("No elements selected. Use 'select' command first.")
        return False

    export_type = input("Export (p)roperties, (l)ayers, or (b)oth? ").lower()
    export_mode = input("Export (s)eparately for each element or (c)ollectively? ").lower()

    if export_type not in ['p', 'l', 'b'] or export_mode not in ['s', 'c']:
        print("Invalid input. Please try again.")
        return False

    elements_to_export = []
    for element in viewer_editor.selected_elements:
        element_data = {
            'Element Name': element.Name,
            'Element GlobalId': element.GlobalId,
            'Element Type': element.is_a(),
            'Element ID': element.id(),
            'Properties': viewer_editor.get_element_properties(element),
            'Layers': []
        }
        if 'HasLayers' in element_data['Properties'] and element_data['Properties']['HasLayers']:
            for i in range(element_data['Properties']['NumberOfLayers']):
                layer = viewer_editor.select_layer(i, element)
                if layer:
                    layer_properties = viewer_editor.get_layer_properties(layer)
                    layer_properties['Layer Number'] = i + 1
                    element_data['Layers'].append(layer_properties)
        elements_to_export.append(element_data)

    # Sort elements by name, GlobalId, and type
    elements_to_export.sort(key=lambda x: (x['Element Name'], x['Element GlobalId'], x['Element Type']))

    if export_mode == 's':
        for element in elements_to_export:
            if export_type in ['p', 'b']:
                export_properties(element, viewer_editor)
            if export_type in ['l', 'b'] and element['Layers']:
                export_layers(element, viewer_editor)
    else:  # collective export
        if export_type in ['p', 'b']:
            export_properties_collectively(elements_to_export, viewer_editor)
        if export_type in ['l', 'b']:
            export_layers_collectively(elements_to_export, viewer_editor)

    return False

def export_properties(element, viewer_editor):
    sanitized_name = sanitize_filename(element['Element Name'])
    filename = f"{sanitized_name}_{element['Element GlobalId']}_properties.csv"
    properties = element['Properties']
    export_to_csv(filename, properties)

def export_layers(element, viewer_editor):
    if not element['Layers']:
        print(f"No layers found for element {element['Element Name']}")
        return
    sanitized_name = sanitize_filename(element['Element Name'])
    filename = f"{sanitized_name}_{element['Element GlobalId']}_layers.csv"
    export_to_csv(filename, element['Layers'])

def export_properties_collectively(elements, viewer_editor):
    filename = "collective_properties.csv"
    data = [{**{'Element Name': e['Element Name'], 'Element GlobalId': e['Element GlobalId'], 'Element Type': e['Element Type']}, **e['Properties']} for e in elements]
    export_to_csv(filename, data)

def export_layers_collectively(elements, viewer_editor):
    filename = "collective_layers.csv"
    data = []
    for element in elements:
        for layer in element['Layers']:
            data.append({**{'Element Name': element['Element Name'], 'Element GlobalId': element['Element GlobalId'], 'Element Type': element['Element Type']}, **layer})
    if data:
        export_to_csv(filename, data)
    else:
        print("No layers found for any selected elements")

def export_to_csv(filename, data):
    if isinstance(data, dict):
        data = [data]
    if not data:
        print(f"No data to export to {filename}")
        return
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = list(data[0].keys())
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow(row)
    print(f"Data exported to {filename}")

def main():
    print("Welcome to the IFC Viewer and Editor.")
    ifc_file = input("Enter the name or path of the IFC file (if in the same directory, just enter the filename): ")
    
    # Check if the file exists in the current directory
    if os.path.exists(ifc_file):
        full_path = os.path.abspath(ifc_file)
    elif os.path.exists(os.path.join(os.getcwd(), ifc_file)):
        full_path = os.path.join(os.getcwd(), ifc_file)
    else:
        print(f"File not found: {ifc_file}")
        return

    print(f"Using IFC file: {full_path}")
    viewer_editor = IFCViewerEditor(full_path)

    print("Type 'help' for a list of commands.")

    while True:
        command = input("\nEnter command (help/select/view/properties/layers/update/save/count/list/export/quit): ").lower()

        if command == 'help':
            print_help()
        elif command == 'select':
            if select_helper(viewer_editor):
                break
            viewer_editor.selected_layer = None  # Reset layer selection when selecting a new element
        elif command == 'view':
            view_helper(viewer_editor)
        elif command == 'properties':
            properties_helper(viewer_editor)
        elif command == 'layers':
            if layers_helper(viewer_editor):
                break
        elif command == 'update':
            if viewer_editor.selected_elements:
                while True:
                    property_name = input("Enter property name (or 'list' to see properties, 'back' to return): ")
                    if property_name.lower() == 'back':
                        break
                    if property_name.lower() == 'list':
                        properties_helper(viewer_editor)
                        continue
                    new_value = input("Enter new value: ")
                    if viewer_editor.update_element_property(viewer_editor.selected_elements, property_name, new_value):
                        print(f"Updated {property_name} to {new_value} for selected element(s)")
                        save_prompt = input("Do you want to save changes now? (y/n): ").lower()
                        if save_prompt == 'y':
                            if viewer_editor.save_ifc_file():
                                print("Changes saved successfully.")
                            else:
                                print("Failed to save changes.")
                    else:
                        print(f"Failed to update property {property_name}. Make sure the property exists and is editable.")
            else:
                print("No elements selected. Use 'select' command first.")
        elif command == 'save':
            confirm = input("Are you sure you want to save changes? This will overwrite the existing file. (y/n): ").lower()
            if confirm == 'y':
                if viewer_editor.save_ifc_file():
                    print("Changes saved successfully.")
                else:
                    print("Failed to save changes.")
            else:
                print("Save operation cancelled.")
        elif command == 'count':
            if count_helper(viewer_editor):
                break
        elif command == 'list':
            element_types = viewer_editor.list_all_element_types()
            print("All element types in the IFC file:")
            for element_type in element_types:
                print(f"  {element_type}")
        elif command == 'export':
            if export_helper(viewer_editor):
                break
        elif command == 'quit':
            if confirm_quit():
                break
        else:
            print("Invalid command. Please try again.")

if __name__ == "__main__":
    main()