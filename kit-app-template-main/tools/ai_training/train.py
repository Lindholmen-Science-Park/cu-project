#!/usr/bin/env python3
"""
AI Training Script for Younite AI Orchestrator

This script converts training examples from examples.jsonl into formats suitable for
fine-tuning with Ollama or OpenAI, and initiates the training process.

Usage:
    python train.py --provider ollama --model llama3.1
    python train.py --provider openai --model gpt-4o-mini
"""

import os
import json
import argparse
import sys
from pathlib import Path


def load_examples(examples_path: Path):
    """Load training examples from JSONL file."""
    examples = []
    if not examples_path.exists():
        print(f"ERROR: Training examples file not found: {examples_path}")
        return examples
    
    with open(examples_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                example = json.loads(line)
                examples.append(example)
            except json.JSONDecodeError as e:
                print(f"WARNING: Skipping invalid JSON on line {line_num}: {e}")
    
    print(f"Loaded {len(examples)} training examples")
    return examples


def convert_to_openai_format(examples):
    """Convert examples to OpenAI fine-tuning format."""
    formatted = []
    for ex in examples:
        user_input = ex.get("input", "")
        response = ex.get("response", {})
        
        # New simplified format: {poi_id, should_move, text?}
        poi_id = response.get("poi_id")
        should_move = response.get("should_move", False)
        text = response.get("text")
        
        # Create the response JSON that the model should produce
        assistant_response = {}
        if poi_id is None:
            # Unknown query - return text response
            assistant_response = {"poi_id": None, "text": text or "I'm a tour guide for Gothenburg. I can help you explore locations."}
        else:
            # Location query
            assistant_response = {"poi_id": str(poi_id), "should_move": bool(should_move)}
        
        assistant_content = json.dumps(assistant_response, ensure_ascii=False)
        
        formatted.append({
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful tour guide assistant for Gothenburg. Respond ONLY as JSON with format: {poi_id: string|null, should_move: boolean, text?: string}."
                },
                {
                    "role": "user",
                    "content": user_input
                },
                {
                    "role": "assistant",
                    "content": assistant_content
                }
            ]
        })
    
    return formatted


def convert_to_ollama_modelfile(examples):
    """Convert examples to Ollama Modelfile format."""
    lines = []
    lines.append("FROM llama3.1")
    lines.append("")
    lines.append("# System prompt")
    lines.append('SYSTEM """You are a helpful tour guide assistant for Gothenburg.')
    lines.append('Respond ONLY as JSON with format: {poi_id: string|null, should_move: boolean, text?: string}.')
    lines.append('If poi_id is set: use should_move (true=go_to, false=describe_location).')
    lines.append('If poi_id is null: return text response for unknown queries.')
    lines.append('"""')
    lines.append("")
    lines.append("# Training examples")
    
    for ex in examples:
        user_input = ex.get("input", "")
        response = ex.get("response", {})
        
        poi_id = response.get("poi_id")
        should_move = response.get("should_move", False)
        text = response.get("text")
        
        # Create response JSON
        if poi_id is None:
            assistant_response = {"poi_id": None, "text": text or "I'm a tour guide for Gothenburg."}
        else:
            assistant_response = {"poi_id": str(poi_id), "should_move": bool(should_move)}
        
        assistant_json = json.dumps(assistant_response, ensure_ascii=False)
        
        # Escape quotes in the Modelfile format
        user_escaped = user_input.replace('"', '\\"')
        assistant_escaped = assistant_json.replace('"', '\\"')
        
        lines.append(f'MESSAGE user "{user_escaped}"')
        lines.append(f'MESSAGE assistant "{assistant_escaped}"')
        lines.append("")
    
    return "\n".join(lines)


def save_openai_training_file(formatted_examples, output_path: Path):
    """Save examples in OpenAI JSONL format."""
    with open(output_path, 'w', encoding='utf-8') as f:
        for ex in formatted_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + '\n')
    print(f"Saved OpenAI training file: {output_path}")


def save_ollama_modelfile(modelfile_content, output_path: Path):
    """Save Ollama Modelfile."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(modelfile_content)
    print(f"Saved Ollama Modelfile: {output_path}")


def train_with_openai(training_file: Path, model: str, api_key: str):
    """Initiate OpenAI fine-tuning."""
    try:
        import openai
    except ImportError:
        print("ERROR: OpenAI library not installed. Install with: pip install openai")
        return False
    
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("ERROR: OPENAI_API_KEY environment variable not set")
            print("Set it with: set OPENAI_API_KEY=your_key_here")
            return False
    
    client = openai.OpenAI(api_key=api_key)
    
    print(f"Uploading training file to OpenAI...")
    try:
        # Upload file
        with open(training_file, 'rb') as f:
            uploaded_file = client.files.create(
                file=f,
                purpose='fine-tune'
            )
        print(f"File uploaded: {uploaded_file.id}")
        
        # Create fine-tuning job
        print(f"Creating fine-tuning job for model: {model}...")
        job = client.fine_tuning.jobs.create(
            training_file=uploaded_file.id,
            model=model,
            hyperparameters={
                "n_epochs": 3,
            }
        )
        
        print(f"Fine-tuning job created: {job.id}")
        print(f"Status: {job.status}")
        print(f"Monitor progress at: https://platform.openai.com/finetune")
        print(f"\nTo check status later, use:")
        print(f"  openai api fine_tunes.get -i {job.id}")
        
        return True
    except Exception as e:
        print(f"ERROR: OpenAI fine-tuning failed: {e}")
        return False


def train_with_ollama(modelfile_path: Path, model_name: str):
    """Create and train Ollama model from Modelfile."""
    print(f"Creating Ollama model '{model_name}' from Modelfile...")
    print(f"Modelfile location: {modelfile_path}")
    print(f"\nTo create the model, run:")
    print(f"  ollama create {model_name} -f {modelfile_path}")
    print(f"\nThen test it with:")
    print(f"  ollama run {model_name}")
    print(f"\nTo use it in your app, set environment variable:")
    print(f"  set MODEL={model_name}")
    
    # Optionally try to run the command automatically
    import subprocess
    import platform
    
    # Try to find ollama executable
    ollama_cmd = "ollama"
    if platform.system() == "Windows":
        # Try common Windows installation paths
        import os
        user_profile = os.environ.get("USERPROFILE", "")
        common_paths = [
            os.path.join(user_profile, "AppData", "Local", "Programs", "Ollama", "ollama.exe"),
            os.path.join("C:", "Program Files", "Ollama", "ollama.exe"),
        ]
        for path in common_paths:
            if os.path.exists(path):
                ollama_cmd = path
                break
    
    try:
        result = subprocess.run(
            [ollama_cmd, "create", model_name, "-f", str(modelfile_path)],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"\nSUCCESS: Model '{model_name}' created!")
            print(f"Output: {result.stdout}")
            return True
        else:
            print(f"\nWARNING: ollama create command failed:")
            print(f"Error: {result.stderr}")
            print(f"\nYou may need to run the command manually (see above).")
            return False
    except FileNotFoundError:
        print("\nWARNING: 'ollama' command not found.")
        print("Make sure Ollama is installed.")
        print("Download from: https://ollama.ai")
        if platform.system() == "Windows":
            print(f"\nTried to find Ollama at common Windows paths but couldn't.")
            print("You may need to add Ollama to your PATH or restart your terminal.")
        return False
    except Exception as e:
        print(f"\nWARNING: Failed to run ollama create: {e}")
        print("You may need to run the command manually (see above).")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Train AI model for Younite AI Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Train with Ollama (default)
  python train.py

  # Train with specific Ollama model
  python train.py --provider ollama --model llama3.2

  # Train with OpenAI
  python train.py --provider openai --model gpt-4o-mini

  # Just convert files without training
  python train.py --provider ollama --convert-only
        """
    )
    
    parser.add_argument(
        "--provider",
        choices=["ollama", "openai"],
        default="ollama",
        help="AI provider to use (default: ollama)"
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name (default: llama3.1 for Ollama, gpt-4o-mini for OpenAI)"
    )
    parser.add_argument(
        "--examples",
        type=Path,
        default=None,
        help="Path to examples.jsonl file"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for converted training files"
    )
    parser.add_argument(
        "--convert-only",
        action="store_true",
        help="Only convert files, don't start training"
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="OpenAI API key (or set OPENAI_API_KEY env var)"
    )
    
    args = parser.parse_args()
    
    # Determine paths (training data lives next to this script)
    script_dir = Path(__file__).parent
    data_dir = script_dir / "data"
    
    examples_path = args.examples or (data_dir / "examples.jsonl")
    output_dir = args.output_dir or (script_dir / "output")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Set default model
    if not args.model:
        args.model = "llama3.1" if args.provider == "ollama" else "gpt-4o-mini"
    
    print("=" * 60)
    print("Younite AI Orchestrator - Training Script")
    print("=" * 60)
    print(f"Provider: {args.provider}")
    print(f"Model: {args.model}")
    print(f"Examples: {examples_path}")
    print(f"Output: {output_dir}")
    print("=" * 60)
    print()
    
    # Load examples
    examples = load_examples(examples_path)
    if not examples:
        print("ERROR: No training examples found. Exiting.")
        return 1
    
    # Convert and save
    if args.provider == "openai":
        formatted = convert_to_openai_format(examples)
        training_file = output_dir / "openai_training.jsonl"
        save_openai_training_file(formatted, training_file)
        
        if not args.convert_only:
            success = train_with_openai(training_file, args.model, args.api_key)
            if not success:
                return 1
    else:  # ollama
        modelfile_content = convert_to_ollama_modelfile(examples)
        modelfile_path = output_dir / "Modelfile"
        save_ollama_modelfile(modelfile_content, modelfile_path)
        
        if not args.convert_only:
            model_name = f"{args.model}-younite"
            success = train_with_ollama(modelfile_path, model_name)
            if not success:
                return 1
    
    print("\n" + "=" * 60)
    print("Training setup complete!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())

