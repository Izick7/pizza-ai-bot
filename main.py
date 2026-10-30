import os
import json
import sys
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv

load_dotenv()

MODEL_NAME = "meta-llama/llama-3.1-8b-instruct"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


# THE SCHEMA 
class CustomerOrderSummary(BaseModel):
    customer_name: str = Field(description="The user's name if provided, otherwise 'Unknown'.")
    ordered_items: list[str] = Field(description="List of all items the user wants to buy.")
    ready_for_checkout: bool = Field(description="Set to True ONLY if all the items they want are confirmed in stock.")
    internal_notes: str = Field(description="A short note about specific user requests and stock status.")


#THE REAL CODE LAYER (The Action Tool)
def check_item_stock(item_name: str) -> str:
    database = {
        "pepperoni pizza": "In Stock",
        "margherita pizza": "In Stock",
        "garlic bread": "In Stock",
        "bbq chicken pizza": "Out of Stock"
    }

    normalized = item_name.strip().lower()

    if normalized == "pizza":
        
        normalized = "pepperoni pizza"
        return (
            "CLARIFICATION NEEDED: The customer requested pizza "
            "without specifying a type. Ask whether they want "
            "pepperoni pizza, margherita pizza, or BBQ chicken pizza."
        )

    status = database.get(normalized, "Out of Stock")

    return f"DATABASE LOG -> '{normalized}' is currently {status}."

tools_list = [
    {
        "type": "function",
        "function": {
            "name": "check_item_stock",
            "description": "Checks the live warehouse database to see if an item is available.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {"type": "string", "description": "The name of the food item."}
                },
                "required": ["item_name"],
            },
        },
    }
]


api_key = os.getenv("OPENROUTER_API_KEY")

def get_client() -> OpenAI:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("Set the OPENROUTER_API_KEY environment variable before running the bot.")
    return OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)

# THE LIVE RUN EXECUTION LOOP

def run_playground():
    client = get_client()
    print(f"Starting OpenRouter AI playground ({MODEL_NAME})", file=sys.stderr)

    print("What would you like to order?", file=sys.stderr)
    user_prompt = input().strip()

    if not user_prompt:
        raise ValueError("Please enter an order.")

    if user_prompt.lower() == "pizza":
        print(
            "Which pizza would you like: "
            "Pepperoni, Margherita, or BBQ Chicken?",
            file=sys.stderr
        )
        user_prompt = input("Your choice: ").strip()

        if not user_prompt:
            raise ValueError("Please choose a pizza type.")

        user_prompt = f"I want {user_prompt} pizza"

    print(f"User prompt: {user_prompt}", file=sys.stderr)
    messages = [
        {
            "role": "system",
            "content": (
                "You are a pizza ordering assistant. Check the stock of every item the customer "
                "requests using check_item_stock before summarizing. Preserve the customer's name "
                "and special requests. Never claim an item is in stock unless the tool confirms it."
            ),
        },
        {"role": "user", "content": user_prompt},
    ]
    stock_checks: dict[str, bool] = {}
    checked_items: dict[str, str] = {}

    # TOOL EXECUTION LOOP
    for _ in range(8):
        print("Checking the order and any requested stock lookups...", file=sys.stderr)
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=tools_list,
            tool_choice="auto"
        )
        
        
        if not response.choices:
            raise RuntimeError(
                f"OpenRouter returned no choices. Response: {response.model_dump_json()}"
      )

        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls
        if not tool_calls:
            if response_message.content:
                messages.append({"role": "assistant", "content": response_message.content})
            break

        assistant_msg = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": tool_call.type,
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in tool_calls
            ],
        }

        if response_message.content:
            assistant_msg["content"] = response_message.content
        messages.append(assistant_msg)

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            if function_name != "check_item_stock":
                raise ValueError(f"Unsupported tool requested by the model: {function_name}")

            raw_arguments = tool_call.function.arguments

            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                print(f"Malformed tool arguments: {raw_arguments!r}", file=sys.stderr)
                raise ValueError("The model returned invalid tool-call JSON.") from exc
            if not isinstance(arguments, dict):
                raise ValueError(f"Invalid arguments for {function_name}: expected a JSON object.")
            item = arguments.get("item_name")
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"Invalid arguments for {function_name}: item_name must be a non-empty string.")

            print(f"Checking stock for {item!r}", file=sys.stderr)
            tool_output = check_item_stock(item)
            normalized_item = item.strip().casefold()
            stock_checks[normalized_item] = tool_output.endswith("currently In Stock.")
            checked_items[normalized_item] = item.strip()
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": function_name,
                "content": tool_output,
            })
    else:
        raise RuntimeError("The model exceeded the maximum number of tool-call rounds.")

    # STRUCTURED OUTPUT GENERATION
    print("Generating the structured order summary...", file=sys.stderr)

    messages.append({
        "role": "user",
        "content": (
            "Summarize the complete interaction. Use the stock-check results for every requested item; "
            "ready_for_checkout is true only if every requested item is confirmed in stock. Preserve "
            "special requests in internal_notes. Return one JSON object containing these four keys with "
            "actual values (not a schema or field descriptions): customer_name (string), "
            "ordered_items (array of strings), ready_for_checkout (boolean), and internal_notes (string). "
            'For example: {"customer_name":"Alex","ordered_items":["Garlic Bread"],'
            '"ready_for_checkout":true,"internal_notes":"No special requests."} '
            "Do not include a properties object, schema metadata, or Markdown."
        )
    })

    summary = None
    for attempt in range(2):
        final_response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            response_format={"type": "json_object"}
        )

        raw_json_string = final_response.choices[0].message.content
        if not raw_json_string:
            if attempt == 1:
                print(
                    "The model returned an empty summary twice; building a safe summary from the completed stock checks.",
                    file=sys.stderr,
                )
                break
            messages.extend([
                {"role": "assistant", "content": ""},
                {
                    "role": "user",
                    "content": (
                        "Your previous response was empty. Return an actual order summary JSON object with "
                        "customer_name, ordered_items, ready_for_checkout, and internal_notes."
                    ),
                },
            ])
            continue

        try:
            summary = CustomerOrderSummary.model_validate_json(raw_json_string)
            break
        except ValidationError:
            if attempt == 1:
                print(
                    "The model returned a schema instead of an order summary twice; "
                    "building a safe summary from the completed stock checks.",
                    file=sys.stderr,
                )
                break
            messages.extend([
                {"role": "assistant", "content": raw_json_string},
                {
                    "role": "user",
                    "content": (
                        "Your previous response was not an order summary. It contained a schema definition. "
                        "Return actual values in a JSON object with exactly these fields: "
                        '{"customer_name":"Unknown","ordered_items":[],"ready_for_checkout":false,'
                        '"internal_notes":"..."} . Do not return properties, titles, types, descriptions, '
                        "or any schema metadata."
                    ),
                },
            ])

    if summary is None:
        summary = CustomerOrderSummary(
            customer_name="Unknown",
            ordered_items=list(checked_items.values()),
            ready_for_checkout=False,
            internal_notes=(
                f"Customer request: {user_prompt}. Stock status: "
                + "; ".join(
                    f"{item}: {'in stock' if stock_checks[key] else 'out of stock'}"
                    for key, item in checked_items.items()
                )
                + "."
            ),
        )

    checked_item_names = {
        name.strip().casefold()
        for name in checked_items.values()
    }

    summary.ready_for_checkout = (
        summary.ready_for_checkout
        and bool(summary.ordered_items)
        and all(
            item.strip().casefold() in checked_item_names
            and stock_checks.get(item.strip().casefold(), False)
            for item in summary.ordered_items
        )
    )
    print(summary.model_dump_json())

if __name__ == "__main__":
    run_playground()
