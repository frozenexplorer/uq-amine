import json

path = "data/raw/piperazine_ermatchkov_2006.json"

with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

block = data["PureOrMixtureData"][0]

print("=== VARIABLES ===")

for i, variable in enumerate(block["Variable"], start=1):
    print(f"\nVariable {i}:")
    print(variable)

print("\n=== PROPERTIES ===")

for i, prop in enumerate(block["Property"], start=1):
    print(f"\nProperty {i}:")
    print(prop)

print("\n=== COMPONENTS ===")

for component in block["Component"]:
    print(component)