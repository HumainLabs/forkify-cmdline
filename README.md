# Forkify Command Line 🍽️

![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg) ![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg) ![Maintained by HumainLabs.ai](https://img.shields.io/badge/Maintained%20by-HumainLabs.ai-orange)

A command-line interface for interacting with Claude AI to process, analyze, and explore documents. Forkify provides an intuitive terminal experience for document analysis with conversation management and system prompt customization.

<p align="center">
  <img src="humainlabs.ai.png" alt="HumainLabs.ai logo" width="50%" />
  <br>
  <a href="https://humainlabs.ai">HumainLabs.ai -- Cognitive Framework Engineering & Research</a>
</p>

## 📋 Table of Contents

* [Overview](#-overview)
* [Features](#-features)
* [Requirements](#-requirements)
* [Installation](#-installation)
* [Usage](#-usage)
* [Command Reference](#-command-reference)
* [Development](#-development)
* [License](#-license)

## 🔍 Overview

Forkify Command Line is a powerful terminal-based application that enables developers and researchers to interact with Claude AI for document analysis. By removing the web and API components, this version focuses exclusively on the command-line experience, providing a lightweight yet powerful tool for document processing tasks.

The command-line version maintains all the core functionality of Forkify while simplifying the deployment and usage experience. Work with your documents directly from your terminal without the need for Docker, web servers, or API endpoints.

## ✨ Features

| Feature | Description |
| ------- | ----------- |
| **Document Processing** | Process and analyze documents with Claude AI |
| **Conversation Management** | Create, switch between, and manage conversations |
| **System Prompt Customization** | Choose different system prompts for different analysis tasks |
| **Response Length Control** | Adjust response length from extremely short to very detailed |
| **Context Window Management** | Control how much of the conversation history is sent to Claude |
| **Document Source Tracking** | View which documents are being used in the current conversation |
| **Token Usage Monitoring** | Track token usage and associated costs |

## 📦 Requirements

* Python 3.8 or higher
* Anthropic API key (for Claude)

## 📥 Installation

### Using git

```bash
# Clone the repository
git clone https://github.com/HumainLabs/forkify-cmdline.git
cd forkify-cmdline

# Run the setup script
./scripts/setup.sh
```

### Configuration

Update the `.env` file with your API keys:

```
ANTHROPIC_API_KEY=your_api_key_here
```

## 🚀 Usage

Start the command-line interface:

```bash
python claude.py
```

Or use the development script:

```bash
./scripts/dev.sh
```

### Working with Documents

1. Place your documents in the `input-docs/main` or create subdirectories for organization
2. Start a conversation with `/sw <name>` to create a new conversation
3. Refer to documents in your queries with `@@filename` syntax
4. Ask questions about your documents

### Sample Session

```
> /sw research_project
Created new conversation 'research_project'
> I need to analyze @@research_paper.pdf
Processing document 'research_paper.pdf'...
Document analysis complete.
> What are the key findings in this paper?
The key findings from the research paper include:
[Claude generates response analyzing the document]
```

## 🧰 Command Reference

| Command | Description |
| ------- | ----------- |
| `/q` | Quit the program |
| `/sw` | List all conversations |
| `/sw <name>` | Create new conversation or switch to existing |
| `/reload` | Reprocess all documents for current conversation |
| `/ld <n>` | Reload documents and update context (default: last 20 messages) |
| `/docs` | Show document sources for current conversation |
| `/p` | List available system prompts |
| `/p <type>` | Switch system prompt type (analysis\|qa\|generation) |
| `/xxs` | Switch to extremely short responses (128 tokens) |
| `/xs` | Switch to very short responses (256 tokens) |
| `/s` | Switch to short responses (512 tokens) |
| `/m` | Switch to medium responses (1024 tokens) |
| `/l` | Switch to long responses (2048 tokens) |
| `/xl` | Switch to very long responses (4096 tokens) |
| `/xxl` | Switch to extremely long responses (8192 tokens) |
| `/clearall` | Clear ALL sessions and conversations (requires confirmation) |
| `/clearconv` | Clear ALL conversations and related files/folders (requires confirmation) |
| `/usage` | Display total token usage and costs |
| `/` | Show help message |

## 🛠️ Development

### Directory Structure

* `input-docs/` - Place your input documents here
* `processed-docs/` - Contains processed document data
* `output-docs/` - Contains output generated from conversations
* `sessions/` - Contains conversation session data
* `data/` - Contains application data
* `scripts/` - Contains utility scripts

### Scripts

* `setup.sh` - Sets up the application environment
* `dev.sh` - Starts the command-line interface

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

Maintained with ❤️ by HumainLabs.ai 