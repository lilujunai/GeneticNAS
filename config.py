import json
import os


def save_config(path_dir, config):
    with open(os.path.join(path_dir, 'config.json'), 'w') as outfile:
        json.dump(config, outfile)


def load_config(path_dir):
    with open(path_dir, 'r') as json_file:
        data = json.load(json_file)
    return data


def default_config():
    return {'batch_size': 256,
            'n_epochs': 310,
            'n_blocks': 2,
            'n_nodes': 5,
            'n_channels': 64,
            'generation_size': 20,
            'population_size': 60,
            'learning_rate': 0.25,
            'weight_decay': 0.0001,
            'dropout': 0.0,
            'LRType': 'MultiStepLR',
            'num_class': 10,
            'momentum': 0.9}
