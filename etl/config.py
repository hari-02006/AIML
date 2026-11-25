import os
import yaml

CONFIG_PATH = "config/etl_config.yaml"

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return yaml.safe_load(f)
    return {
        "input_dir": "data/raw",
        "incoming_dir": "data/incoming",
        "processed_dir": "data/processed",
        "validated_dir": "data/validated",
        "rejected_dir": "data/rejected",
        "log_dir": "logs"
    }
