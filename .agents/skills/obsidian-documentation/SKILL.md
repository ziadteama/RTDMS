---
name: obsidian-documentation
description: Guia para usar o servidor MCP do Obsidian e manter a documentação de Engenharia organizada.
tags: [documentation, obsidian, mcp, knowledge-base]
---

# Obsidian Documentation & MCP Skill

Este skill ensina como interagir com o "Segundo Cérebro" de Engenharia usando o servidor MCP do Obsidian.

## 1. Filosofia: "Knowledge Driven Development"

Não mantenha contexto importante apenas no chat ou na cabeça.

- **Se é uma decisão:** Crie um Checkpoint.
- **Se é um aprendizado:** Crie uma nota na Knowledge Base.
- **Se é status:** Atualize o Checkpoint do projeto.

## 2. Estrutura do Vault

O diretório raiz de engenharia é: `Docs/Engenharia/`

```text
Docs/Engenharia/
├── 00_Dashboard.md          # 🏠 Ponto de partida
├── 10_Active_Projects/      # 🚀 Projetos ativos (ex: Projeto_Backend)
│   └── <Project_Name>/
│       ├── Checkpoints/     # 🛑 Status e dumps de contexto
│       └── Architecture/    # 📐 Desenhos e decisões
├── 20_Knowledge_Base/       # 📚 Conhecimento reutilizável (snippets, guias)
├── 30_Daily_Logs/           # 📅 Notas rápidas do dia
├── 80_Reference/            # 🗄️ Coisas aleatórias, senhas, rascunhos
└── 99_Templates/            # 🧩 Templates padrão
```

## 3. Como usar as Ferramentas MCP

### Ler o contexto atual

Para saber o que está acontecendo sem perguntar ao usuário:
`mcp_obsidian_read_note(path="Docs/Engenharia/00_Dashboard.md")`

### Criar um Checkpoint (Obrigatório ao pausar tarefa)

Ao finalizar ou pausar uma tarefa complexa, crie um checkpoint para não perder o fio da meada.

1. **Leia o template**:
   `mcp_obsidian_read_note(path="Docs/Engenharia/99_Templates/Checkpoint_Template.md")`

2. **Escreva a nota**:
   Use `mcp_obsidian_write_note` com o caminho:
   `Docs/Engenharia/10_Active_Projects/<Projeto>/Checkpoints/YYYY-MM-DD_Nome_Descritivo.md`

### Pesquisar conhecimento

Antes de perguntar "como faz X?", pesquise na base:
`mcp_obsidian_search_notes(query="terraform lambda pattern")`

## 4. Padrões Obrigatórios

1. **Frontmatter**: Todas as notas devem ter tags e status.

   ```yaml
   tags: [checkpoint, python]
   status: active
   ```

2. **Links**: Use `[[WikiLinks]]` para conectar notas.
   - Ex: "Conforme definido em [[Architecture_V2]]..."
3. **Imagens**: Se gerar diagramas (Mermaid), coloque direto na nota.
4. **Append (Logs)**: Para logs diários, use o modo `append` do `write_note` para não sobrescrever o dia.

## 5. Workflow Típico

1. **Início da Sessão**: Ler `00_Dashboard` e o último checkpoint do projeto.
2. **Durante**: Consultar `20_Knowledge_Base`.
3. **Fim da Sessão**: Criar um novo Checkpoint em `10_Active_Projects/.../Checkpoints/`.

## 6. Comandos Úteis

- **Listar Projetos**: `mcp_obsidian_list_directory(path="Docs/Engenharia/10_Active_Projects")`
- **Ler Dashboard**: `mcp_obsidian_read_note(path="Docs/Engenharia/00_Dashboard.md")`
