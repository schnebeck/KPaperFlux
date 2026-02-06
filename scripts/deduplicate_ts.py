import xml.etree.ElementTree as ET
import collections

TS_FILE = 'resources/l10n/de/gui_strings.ts'

def deduplicate_ts():
    print(f"Deduplicating {TS_FILE}...")
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    tree = ET.parse(TS_FILE, parser=parser)
    root = tree.getroot()
    
    contexts = collections.defaultdict(list)
    
    for context in root.findall('context'):
        name = context.find('name').text
        messages = context.findall('message')
        contexts[name].extend(messages)
    
    for ctx in root.findall('context'):
        root.remove(ctx)
        
    sorted_names = sorted(contexts.keys())
    for name in sorted_names:
        new_ctx = ET.SubElement(root, 'context')
        name_elem = ET.SubElement(new_ctx, 'name')
        name_elem.text = name
        
        unique_msgs = {}
        
        for msg in contexts[name]:
            source = msg.find('source').text
            if not source: continue
            
            def get_quality(m):
                t = m.find('translation')
                if t is None: return 0
                if t.get('type') == 'unfinished': return 1
                if not t.text: return 1
                return 2

            if source not in unique_msgs:
                unique_msgs[source] = msg
            else:
                current_q = get_quality(unique_msgs[source])
                new_q = get_quality(msg)
                if new_q > current_q:
                    unique_msgs[source] = msg
        
        for src in sorted(unique_msgs.keys()):
            new_ctx.append(unique_msgs[src])
            
    indent(root)
    tree.write(TS_FILE, encoding='utf-8', xml_declaration=True)
    print(f"Condensed to {len(sorted_names)} unique contexts.")

def indent(elem, level=0):
    i = "\n" + level*"    "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "    "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for subelem in elem:
            indent(subelem, level+1)
        if not elem[-1].tail or not elem[-1].tail.strip():
            elem[-1].tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

if __name__ == "__main__":
    deduplicate_ts()
