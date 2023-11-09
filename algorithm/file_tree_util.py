import os
import os.path as osp

root_path = "/Users/jiawen/Documents/markdown-editor"
dirs = os.listdir(root_path)

skip_node_list = ['.DS_Store']


def get_file_tree(path):
    item_map_list = []
    dir_path = osp.join(root_path, path.strip('""'))
    print(dir_path)
    if not osp.exists(dir_path):
        raise FileNotFoundError(f"No such file or directory: '{dir_path}'")
    item_list = os.listdir(dir_path)
    for item_name in item_list:
        if item_name in skip_node_list:
            continue
        item_path = osp.join(dir_path, item_name)
        item_node = dict()
        item_node["name"] = item_name
        item_node["path"] = osp.join(path,item_name)
        if osp.isdir(item_path):
            item_node["type"] = "folder"
            item_node["children"] = []
        else:
            item_node["type"] = "file"
        item_map_list.append(item_node)
    return item_map_list


print(get_file_tree(""))
