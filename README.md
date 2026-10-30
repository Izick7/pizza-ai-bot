# pizza-ai-bot

A command-line pizza-ordering assistant that uses an OpenRouter chat model to
check item availability and return a structured order summary.

## Requirements

- Python 3.9 or later
- An OpenRouter API key

## Setup

Create and activate a virtual environment, then install the dependencies:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create a `.env` file in the project directory and add your API key:

```dotenv
OPENROUTER_API_KEY=your-openrouter-api-key
```

The application loads `.env` automatically. The file is ignored by Git; do not
commit or share your API key.

## Run

```sh
python main.py
```

Enter an order when prompted. If the order is exactly `pizza`, the program asks
you to choose a type before continuing.

## Inventory and order handling

Stock is checked against the inventory dictionary in `main.py` (it is not a
connected live warehouse or external database):

| Item | Availability |
| --- | --- |
| Pepperoni pizza | In stock |
| Margherita pizza | In stock |
| Garlic bread | In stock |
| BBQ chicken pizza | Out of stock |
| Any unlisted item | Out of stock |

The assistant checks requested items through a tool call. It validates its
final response against the order-summary schema and only marks an order ready
for checkout if the returned items were checked and confirmed in stock. If the
model fails to return a valid summary after a retry, the program prints a
conservative fallback summary.

## Output

Progress messages are written to standard error. Standard output contains one
JSON object with these fields:

- `customer_name` — the customer's name, or `"Unknown"`
- `ordered_items` — the items in the order
- `ready_for_checkout` — whether the items were confirmed in stock
- `internal_notes` — special requests and other order details
