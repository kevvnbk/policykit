# Sandbox Documentation Index

Welcome to the Policy Sandbox documentation. This guide helps you navigate the available documentation based on your needs.

---

## 🚀 Getting Started

**New to the sandbox?** Start here:
1. [Main README](../README.md) - Overview and quick setup
2. [Architecture Overview](architecture/overview.md) - High-level system design
3. [Policy Authoring Guide](guides/policy-authoring-guide.md) - Write your first policy

---

## 📚 Documentation Structure

### [Architecture](architecture/)
System design, structure, and PolicyKit comparison.

- **[ARCHITECTURE_COMPARISON.md](architecture/ARCHITECTURE_COMPARISON.md)** - How sandbox architecture compares to PolicyKit
- **[STRUCTURE.md](architecture/STRUCTURE.md)** - Detailed directory structure and file mappings

### [Guides](guides/)
Step-by-step tutorials and comprehensive documentation for using the sandbox.

- **[policy-authoring-guide.md](guides/policy-authoring-guide.md)** - Complete guide to writing governance policies
- **[test-scenario-guide.md](test-scenario-guide.md)** - Complete guide to writing test scenarios
- **[api_reference.md](guides/api_reference.md)** - Sandbox API reference (ctx.*, event handlers, etc.)
- **[external-documents-guide.md](guides/external-documents-guide.md)** - Working with Google Sheets and external data
- **[google-sheets-implementation.md](guides/google-sheets-implementation.md)** - Technical implementation details
- **[POLICY_GUIDE_README.md](guides/POLICY_GUIDE_README.md)** - Policy guide overview

### [Planning](planning/)
Design documents and integration plans.

- **[sandbox-plan.md](planning/sandbox-plan.md)** - Original sandbox design and implementation plan
- **[POLICYKIT_INTEGRATION_PLAN.md](planning/POLICYKIT_INTEGRATION_PLAN.md)** - Plan for integrating sandbox with PolicyKit

### [Reference](reference/)
Quick references, pipeline details, and technical implementation notes.

- **[policy-quick-reference.md](reference/policy-quick-reference.md)** - Quick reference for policy authoring patterns
- **[test-scenario-quick-reference.md](test-scenario-quick-reference.md)** - Quick reference for test scenarios
- **[revision-quick-reference.md](reference/revision-quick-reference.md)** - Quick reference for revision/validation fixes
- **[pipeline-implementation.md](reference/pipeline-implementation.md)** - Pipeline architecture and validation system
- **[revision-debugging.md](reference/revision-debugging.md)** - Debugging revision issues
- **[revision-process-analysis.md](reference/revision-process-analysis.md)** - Analysis of revision process improvements

---

## 🎯 Documentation by Task

### I want to...

#### Write a governance policy
→ Start: [Policy Authoring Guide](guides/policy-authoring-guide.md)  
→ Quick ref: [Policy Quick Reference](reference/policy-quick-reference.md)  
→ API details: [API Reference](guides/api_reference.md)

#### Write test scenarios
→ Start: [Test Scenario Guide](test-scenario-guide.md)  
→ Quick ref: [Test Scenario Quick Reference](test-scenario-quick-reference.md)

#### Understand the sandbox architecture
→ Overview: [Architecture Comparison](architecture/ARCHITECTURE_COMPARISON.md)  
→ Details: [Directory Structure](architecture/STRUCTURE.md)  
→ Design: [Sandbox Plan](planning/sandbox-plan.md)

#### Work with external data (Google Sheets)
→ Guide: [External Documents Guide](guides/external-documents-guide.md)  
→ Implementation: [Google Sheets Implementation](guides/google-sheets-implementation.md)

#### Debug validation or generation issues
→ Quick fixes: [Revision Quick Reference](reference/revision-quick-reference.md)  
→ Deep dive: [Revision Process Analysis](reference/revision-process-analysis.md)  
→ Debugging: [Revision Debugging](reference/revision-debugging.md)

#### Integrate with PolicyKit
→ Plan: [PolicyKit Integration Plan](planning/POLICYKIT_INTEGRATION_PLAN.md)  
→ Architecture: [Architecture Comparison](architecture/ARCHITECTURE_COMPARISON.md)

#### Understand the pipeline
→ Full details: [Pipeline Implementation](reference/pipeline-implementation.md)  
→ Quick ref: [Revision Quick Reference](reference/revision-quick-reference.md)

---

## 📖 Documentation Types

| Type | Purpose | Audience |
|------|---------|----------|
| **Guides** | Step-by-step instructions and tutorials | All users |
| **Reference** | Quick lookups, cheat sheets | Developers writing policies |
| **Architecture** | System design and structure | Developers, integrators |
| **Planning** | Design decisions and roadmaps | Contributors, maintainers |

---

## 🔗 Related Documentation

- **[Main README](../README.md)** - Sandbox overview and setup
- **[API Integration Guide](../API_INTEGRATION_GUIDE.md)** - Bedrock API authentication
- **[Deployment Guide](../DEPLOYMENT.md)** - Deploying the sandbox
- **[Google OAuth Setup](../GOOGLE_OAUTH_SETUP.md)** - Setting up Google Sheets integration
- **[PolicyKit Integration](../POLICYKIT_INTEGRATION.md)** - Current integration status

---

## 💡 Tips for Using This Documentation

1. **Start broad, go deep**: Begin with guides, use references for lookups
2. **Cross-references**: Documents link to each other - follow the trail
3. **Examples first**: Most guides include working examples
4. **Search**: Use your editor's search (Ctrl+F) to find specific topics
5. **Contribute**: Found a gap? Documentation improvements are welcome!

---

## 📝 Documentation Standards

All documentation in this directory follows these principles:
- **Self-contained**: Each doc stands alone with necessary context
- **Cross-linked**: Related docs reference each other
- **Example-driven**: Real code examples over abstract descriptions
- **Up-to-date**: Updated with code changes (check last modified dates)

---

*Last updated: 2026-09-30*
