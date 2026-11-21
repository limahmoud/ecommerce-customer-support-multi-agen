
from tools import ALL_TOOLS

print("\n========== AVAILABLE TOOLS ==========\n")

for index, current_tool in enumerate(ALL_TOOLS, start=1):
    print(f"{index}. {current_tool.name}")
    print(f"   Description: {current_tool.description}")
    print("-" * 60)


# Test one tool
print("\n========== TEST CUSTOMER TOOL ==========\n")

result = ALL_TOOLS[0].invoke({
    "customer_id": 1
})

print(result)
