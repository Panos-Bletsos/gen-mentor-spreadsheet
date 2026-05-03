import re
import json
from typing import Dict, Any


def convert_json_output(output: str) -> Dict[str, Any]:
    """
    Convert raw JSON output from the LLM into structured format.

    Args:
        output: The JSON output from the LLM
        
    Returns:
        Structured JSON output
    """
    output = output.strip()
    if output.startswith("```json"):
        output = output[7:].strip()
    if output.endswith("```"):
        output = output[:-3].strip()
    if output.endswith("```json"):
        output = output[:-7].strip()
    try:
        # Attempt to parse the output as JSON
        return json.loads(output)
    except json.JSONDecodeError:
        # If parsing fails, try to extract JSON from the output string
        start_idx = output.find('{')
        end_idx = output.rfind('}') + 1
        if start_idx != -1 and end_idx != 0:
            json_str = output[start_idx:end_idx]
            return json.loads(json_str)
        else:
            raise json.JSONDecodeError("No valid JSON found in response", output, 0)

def _content_to_str(content) -> str:
    """Flatten a content value that may be a string or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                # output_text / text blocks
                if block.get("type") in ("text", "output_text"):
                    parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


def get_text_from_response(response):
    """Extract text from the response object."""
    if 'messages' in response:
        return _content_to_str(response['messages'][-1].content)
    if 'message' in response['choices'][0]:
        return response['choices'][0]['message']['content']
    return response['choices'][0]['text']

def extract_think_and_result(info):
    "Extract think and result content from the response info."""
    think_match = re.search(r"<think>(.*?)</think>", info, re.DOTALL)
    think_content = think_match.group(1).strip() if think_match else ''
    result_content = re.sub(r"<think>.*?</think>", "", info, flags=re.DOTALL).strip()
    return think_content, result_content


def preprocess_response(response, only_text=True, exclude_think=False, json_output=False):
    import logging
    logger = logging.getLogger(__name__)

    if only_text or exclude_think or json_output:
        response = get_text_from_response(response)
    if exclude_think:
        think_content, result_content = extract_think_and_result(response)
        response = result_content
    if json_output:
        try:
            response = convert_json_output(response)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON output: %s\nRaw response: %s", str(e), response[:500])
            response = {"error": "Invalid JSON output", "raw_content": response}
            raise e
    return response

