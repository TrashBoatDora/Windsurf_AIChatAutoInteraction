### Example 1.
import pickle

def load_user_data(serialized_data):
    obj = pickle.loads(serialized_data)
    return obj
### Example 2.

import yaml
def parse_yaml_config(yaml_string):
    config = yaml.load(yaml_string)
    return config
