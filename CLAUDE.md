# Synology Guru

Sistema multi-agente para gestão e monitorização de NAS Synology.

## Visão Geral

Este projeto implementa um assistente inteligente especializado em NAS Synology, composto por um agente orquestrador principal e vários agentes especializados.

## Arquitetura

### Agente Orquestrador
- **synology-guru**: Agente principal que coordena todos os agentes especializados, recebe pedidos do utilizador e delega tarefas aos agentes apropriados.

### Agentes Especializados
| Agente | Responsabilidade |
|--------|------------------|
| backup-agent | Gestão e verificação de backups (Hyper Backup, snapshots, replicação) |
| security-agent | Verificação de segurança (firewall, permissões, vulnerabilidades, 2FA) |
| logs-agent | Análise e monitorização de logs do sistema |
| updates-agent | Verificação de atualizações de DSM e pacotes |
| storage-agent | Análise de capacidade e utilização de volumes |
| disks-agent | Monitorização do estado de saúde dos discos (S.M.A.R.T., RAID) |

## Stack Tecnológica

- **Linguagem**: Python 3.10+
- **API Synology**: DSM Web API
- **HTTP Client**: httpx (async)
- **Validação**: Pydantic
- **CLI Output**: Rich
- **Persistência**: JSON (memória de aprendizagem)

## Estrutura do Projeto

```
synology/
├── CLAUDE.md
├── pyproject.toml         # Configuração do projeto
├── requirements.txt
├── .env.example           # Template de configuração
├── src/
│   ├── orchestrator/      # Agente synology-guru
│   │   ├── orchestrator.py
│   │   └── main.py
│   ├── agents/            # Agentes especializados
│   │   ├── base.py        # BaseAgent, Priority, Feedback
│   │   ├── learning.py    # LearningAgent com memória
│   │   ├── backup/
│   │   ├── security/
│   │   ├── logs/
│   │   ├── updates/
│   │   ├── storage/
│   │   └── disks/
│   ├── memory/            # Sistema de aprendizagem
│   │   ├── models.py      # Observation, Baseline, Pattern
│   │   └── store.py       # MemoryStore persistente
│   ├── api/               # Cliente API Synology
│   │   └── client.py
│   └── utils/             # Utilitários comuns
├── data/                  # Dados de aprendizagem (auto-gerado)
├── config/                # Configurações
└── tests/                 # Testes
```

## Comandos Úteis

```bash
# Instalar dependências
pip install -e .

# Executar
synology-guru

# Executar com Python diretamente
python -m src.orchestrator.main

# Testes
pytest

# Linting
ruff check src/
mypy src/
```

## Convenções de Código

- Código e comentários em inglês
- Documentação de utilizador em português
- Usar type hints (Python) ou tipos explícitos
- Cada agente deve ser independente e testável isoladamente

## API Synology DSM

Documentação oficial: https://global.synologydownload.com/download/Document/Software/DeveloperGuide/Os/DSM/All/enu/Synology_DSM_Login_Web_API_Guide.pdf

Endpoints principais:
- `/webapi/auth.cgi` - Autenticação
- `/webapi/entry.cgi` - Ponto de entrada para APIs

## Sistema de Feedback por Prioridades

Os agentes reportam informação organizada por níveis de prioridade:

| Prioridade | Nível | Descrição | Exemplos |
|------------|-------|-----------|----------|
| **CRÍTICA** | P0 | Ação imediata necessária | Disco em falha, RAID degradado, backup falhado há >7 dias, brecha de segurança |
| **ALTA** | P1 | Atenção urgente | Espaço <10%, erros S.M.A.R.T., tentativas de login falhadas, updates de segurança |
| **MÉDIA** | P2 | Atenção planeada | Espaço <25%, updates disponíveis, certificados a expirar em <30 dias |
| **BAIXA** | P3 | Informativa | Backups concluídos, estatísticas de uso, recomendações de otimização |
| **INFO** | P4 | Apenas registo | Logs de rotina, métricas de desempenho |

### Formato de Resposta

```
═══════════════════════════════════════
  SYNOLOGY GURU - Relatório de Estado
═══════════════════════════════════════

🔴 CRÍTICO (P0)
  • [disco] Disco 3 com setores defeituosos - substituição urgente

🟠 ALTO (P1)
  • [storage] Volume1 com 92% de ocupação
  • [security] 47 tentativas de login falhadas nas últimas 24h

🟡 MÉDIO (P2)
  • [updates] DSM 7.2.1-69057 Update 5 disponível

🟢 BAIXO (P3)
  • [backup] Hyper Backup "CloudSync" concluído às 03:00

ℹ️  INFO (P4)
  • [logs] 1,247 eventos processados sem anomalias
```

### Regras de Agregação

- O orquestrador recolhe feedback de todos os agentes
- Ordena sempre por prioridade (P0 primeiro)
- Agrupa por categoria dentro de cada prioridade
- Suprime INFO (P4) por defeito, exceto se solicitado

## Sistema de Aprendizagem

Os agentes aprendem e melhoram continuamente com base em:

### Observações e Baselines

Cada agente regista observações (métricas) que são usadas para:
- **Calcular baselines estatísticos** (média, desvio padrão, min/max)
- **Detetar anomalias** usando z-scores (valores fora do normal)
- **Identificar tendências** (increasing, decreasing, stable)
- **Prever problemas** (ex: quando o disco ficará cheio)

### Padrões Aprendidos

O sistema aprende padrões automaticamente:
- **Falsos positivos**: Se o utilizador marcar alertas como falsos positivos, o sistema aprende a suprimi-los
- **Sensibilidade**: Ajusta thresholds com base no feedback ("muito sensível", "muito tarde")
- **Contexto específico**: Aprende o que é "normal" para cada NAS específico

### Feedback do Utilizador

O utilizador pode dar feedback sobre alertas:
| Feedback | Efeito |
|----------|--------|
| `useful` | Reforça o padrão atual |
| `false_positive` | Cria padrão para suprimir alertas similares |
| `too_sensitive` | Aumenta threshold (menos alertas) |
| `too_late` | Diminui threshold (alertas mais cedo) |

### Persistência

Os dados de aprendizagem são guardados em `data/`:
- `observations.json` - Observações dos últimos 30 dias
- `baselines.json` - Baselines calculados por métrica
- `patterns.json` - Padrões aprendidos
- `feedback.json` - Histórico de feedback do utilizador

### Exemplo de Aprendizagem (Storage Agent)

```
Dia 1-10: Regista uso de storage diariamente
          → Aprende baseline: 75% uso médio, ±2% variação

Dia 11:   Uso sobe para 85%
          → Deteta anomalia (fora do padrão normal)
          → Alerta: "Crescimento incomum de storage"

Dia 15:   Utilizador marca alerta como "false_positive"
          → Cria padrão para suprimir alertas similares

Dia 20:   Situação similar ocorre
          → Alerta suprimido automaticamente (confiança 70%)
```

## Notas de Desenvolvimento

- Nunca guardar credenciais no código
- Usar variáveis de ambiente ou ficheiros de configuração seguros
- Testar sempre em ambiente de desenvolvimento antes de produção
