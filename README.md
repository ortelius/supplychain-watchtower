# Supplychain Watchtower

> Part of the **Cybersecurity Neighborhood Watch** initiative by [Ortelius](https://github.com/ortelius)

## Overview

**Supplychain Watchtower** is a GitHub Actions–driven automation service that monitors new releases across open-source projects, updates the Ortelius database, and triggers CI/CD pipelines using the Ortelius CLI.  
It leverages **AI Model Context Protocol (AI MCP) agents** to automatically update package dependency files in forked repositories, ensuring the software supply chain stays secure and current.

## Purpose

This repo powers the **Cybersecurity Neighborhood Watch** initiative, a community effort to:
- 🕵️ Detect and track upstream package releases  
- 📦 Maintain accurate supply chain metadata in Ortelius  
- 🤖 Automate dependency updates with AI MCP agents  
- 🔒 Strengthen software supply chain security  

## How It Works

1. **Monitor Releases**  
   GitHub Actions listen for new releases in watched repositories.  

2. **Update Ortelius Database**  
   Supply chain data is synced into the Ortelius database.  

3. **Trigger CI/CD**  
   Pipelines are generated via the Ortelius CLI and executed.  

4. **Automated Dependency Updates**  
   AI MCP agents fork repos and update dependency files automatically.  

## Getting Started

Clone this repo and install dependencies:

```bash
git clone https://github.com/ortelius/supplychain-watchtower.git
cd supplychain-watchtower
