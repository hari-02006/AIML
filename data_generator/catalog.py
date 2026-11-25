
def generate_catalog(config):
    products = config['products']
    categories = [{"category_name": c} for c in config['categories']]
    return products, categories
