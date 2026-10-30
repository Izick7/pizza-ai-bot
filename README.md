# pizza-ai-bot

## Run

Install the packages from `requirements.txt`, set an OpenRouter API key, then run:

```sh
export OPENROUTER_API_KEY="your-openrouter-api-key"
python main.py
```

The program writes progress messages to standard error and prints one JSON order
summary to standard output with `customer_name`, `ordered_items`,
`ready_for_checkout`, and `internal_notes`. Stock is checked for each item
requested, and the JSON is validated against the summary schema before it is
printed. If the model returns a schema instead of an order summary, the bot
asks once for a corrected response, then falls back to a conservative summary
from the completed stock checks rather than crashing. Enter the order when
prompted; an empty order is rejected.
