#!/usr/bin/env python3
"""
Debug script for category key lookup
Tests how category names are being normalized and looked up in config
"""

import yaml

def load_config():
    """Load config.yaml"""
    with open('config.yaml', 'r') as f:
        return yaml.safe_load(f)

def normalize_category_key(category):
    """Convert category name to config key format"""
    return category.lower().replace(' ', '_').replace('-', '_')

def test_category_lookup():
    """Test category lookups"""
    config = load_config()
    
    # Test categories
    test_categories = [
        "women_dress",
        "Women Dress",
        "outfit sets",
        "Outfit Sets",
        "women_top",
        "Women Top"
    ]
    
    print("=" * 70)
    print("TESTING CATEGORY KEY LOOKUPS")
    print("=" * 70)
    print()
    
    # Show what's in config
    print("Keys in config['size_mappings']:")
    for key in config.get('size_mappings', {}).keys():
        print(f"  - '{key}'")
    print()
    
    print("Keys in config['shopify_categories']:")
    for key in config.get('shopify_categories', {}).keys():
        print(f"  - '{key}'")
    print()
    
    # Test each category
    print("=" * 70)
    print("TESTING LOOKUPS:")
    print("=" * 70)
    
    for category in test_categories:
        normalized = normalize_category_key(category)
        
        # Look up size mapping
        size_map = config.get('size_mappings', {}).get(normalized, 'NOT FOUND')
        
        # Look up shopify category
        shopify_cat = config.get('shopify_categories', {}).get(normalized, 'NOT FOUND')
        
        print(f"\nInput: '{category}'")
        print(f"  Normalized key: '{normalized}'")
        print(f"  Size mapping: {size_map}")
        print(f"  Shopify category: {shopify_cat}")

if __name__ == "__main__":
    test_category_lookup()