---
name: readme-writer
description: Analyzes repository contents and generates extremely detailed README files in Markdown. Use when the user requests a README, repository documentation, project overview, or repository information.
---

# README Writer

Generates comprehensive README files in Markdown by analyzing the repository with all available tools, then filling a required structure including repository structure and flow chart.

## When to Use

Apply this skill when the user:

- Asks for a README or to write/create a README
- Requests repository documentation or project overview
- Asks for "information about the repository" or similar
- Requests a "full" or "detailed" README (include Changelog from commit history when appropriate)

Before generating the README, always gather information first (see below). Do not write the README from assumptions only.

## Before Writing: Gather Information

Use every relevant tool to collect data; then fill all README sections from that data.

1. **Search the codebase**
   - Semantic search / grep for: entry points, main modules, configuration loading, dependency files (e.g. package.json, pyproject.toml, requirements.txt, go.mod, Cargo.toml).
   - Identify technologies, features, and how components interact.

2. **Explore structure**
   - List directories and key files (Glob/list_dir). Build the full tree of the repository (folders and important files).

3. **Read key files**
   - Root: existing README (if any), LICENSE, config files, dependency manifests.
   - Selected source files to understand purpose, stack, and data/request flow.

4. **Commit history (for Changelog)**
   - If the user asked for a full README or changelog: retrieve commit history (e.g. git log or available MCP/terminal) and summarize changes for the Changelog section.

Use the collected data to populate Overview, Features, Installation, Usage, Technologies, Configuration, Requirements, Repository Structure, and Flow Chart.

## Required README Structure

Use the following sections with the given emojis. Fill each from the gathered information.

| Section | Emoji | Content |
|--------|--------|--------|
| Overview | 📖 | Clear, concise project description (1–2 paragraphs). |
| Features | ✨ | List of key features and functionalities. |
| Installation | 🚀 | Step-by-step installation (clone, dependencies, commands). |
| Usage | 🛠️ | Examples and instructions for using the project. |
| Technologies | 📦 | Main technologies and programming languages used. |
| Configuration | 🔧 | Configuration, environment variables, options. |
| Requirements | ✅ | Prerequisites to run the project (runtime versions, services). |
| Contributing | 🤝 | How to contribute (link to CONTRIBUTING or short guidelines). |
| Documentation | 📄 | Links or pointers to more detailed documentation. |
| Acknowledgements | ❤️ | Credits and acknowledgements. |
| Changelog | 📝 | Summary of changes from commit history (when user asked for full README or changelog). |

## Mandatory Additional Sections

- **Repository Structure:** Include the complete structure of the repository (folders and files). For each part, provide a brief explanation of its purpose and role in the project (e.g. `src/api/` — REST API; `config/` — environment configuration).

- **Flow Chart:** Include a flow chart or diagram of how components interact (e.g. modules, data flow, request flow). Prefer **Mermaid** (flowchart or sequence). If Mermaid is not feasible, use ASCII. If the codebase does not make relationships obvious, describe them in text and add a simplified diagram where possible.

## README Template

Use this template; replace placeholders with content from the analysis.

```markdown
# [Project Name]

## 📖 Overview

[Clear, concise description of the project in 1–2 paragraphs.]

## ✨ Features

- [Feature 1]
- [Feature 2]
- [Feature 3]

## 🚀 Installation

[Step-by-step instructions: clone, install dependencies, any setup commands.]

## 🛠️ Usage

[Examples and instructions on how to use the project.]

## 📦 Technologies

[List of main technologies and programming languages used.]

## 🔧 Configuration

[Configuration, environment variables, and relevant options.]

## ✅ Requirements

[Prerequisites: runtime versions, services, tools.]

## 🤝 Contributing

[Guidelines for contributing or link to CONTRIBUTING.]

## 📄 Documentation

[Links or instructions for more detailed documentation.]

## ❤️ Acknowledgements

[Credits and acknowledgements.]

## 📝 Changelog

[Summary of changes based on commit history; omit if not requested.]

## 🗂️ Repository Structure

[Complete structure with short explanation per part.]

\`\`\`
[Tree or list of folders and key files]
\`\`\`

[Brief purpose for each major folder or file.]

## 🔗 Flow Chart

[Diagram using Mermaid or ASCII showing component interconnection and data/flow.]

\`\`\`mermaid
flowchart LR
  A[Component A] --> B[Component B]
  B --> C[Component C]
\`\`\`
```

## Formatting Rules

- Output only valid Markdown.
- Use the section emojis in headings as in the table and template.
- Put code and commands in fenced blocks with the correct language (e.g. `bash`, `python`).
- Use relative links to files or docs where appropriate; ensure links are valid.
- Use forward slashes in paths (e.g. `scripts/helper.py`), not backslashes.