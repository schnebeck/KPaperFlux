
import json
from pathlib import Path

def cleanup():
    path = Path("filter_tree.json")
    if not path.exists():
        return
    
    with open(path, "r") as f:
        tree = json.load(f)
    
    def clean_nodes(nodes):
        new_nodes = []
        for n in nodes:
            name = n.get("name", "").strip()
            # Delete if it matches test names or is the legacy folder
            is_trash = (name in ["Test List", "All Visible", "Imported (Legacy)"])
            
            # Check for dummy data u1/u2
            if not is_trash and n.get("type") == "filter":
                data_str = json.dumps(n.get("data", {}))
                if '"u1"' in data_str or '"u2"' in data_str:
                    is_trash = True
            
            if is_trash:
                continue
                
            if "children" in n and n["children"]:
                n["children"] = clean_nodes(n["children"])
            
            new_nodes.append(n)
        return new_nodes

    if "root" in tree and "children" in tree["root"]:
        tree["root"]["children"] = clean_nodes(tree["root"]["children"])
    
    with open(path, "w") as f:
        json.dump(tree, f, indent=2)
    
    print("Cleanup done.")

if __name__ == "__main__":
    cleanup()
