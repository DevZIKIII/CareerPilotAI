# CareerPilot AI

## Estado desta publicação

Snapshot público de um projeto pessoal em desenvolvimento. O radar de vagas está em revisão e pode ser lento ou retornar resultados pouco relevantes. Não há garantia de precisão, cobertura ou disponibilidade dos serviços externos.

Esta distribuição inclui apenas código e documentação, sem currículos, bancos, logs, credenciais ou histórico privado. Configure suas próprias variáveis de ambiente; nunca versione o arquivo .env. Não configure SMTP para testar os exemplos: revise destinatários e conteúdo antes de qualquer envio real. A integração com IA pode transmitir o texto de currículos a um provedor externo e gerar custos; use somente dados fictícios até compreender esse fluxo.

O projeto ainda não tem uma suíte automatizada completa. A publicação não significa homologação para uso em produção.

CareerPilot AI é um aplicativo desktop Windows feito com Python, PySide6 e SQLite para organizar currículos, vagas, análises de compatibilidade por IA e histórico de candidaturas.

O aplicativo não é um site, não depende de navegador para funcionar e não automatiza candidaturas em plataformas de emprego.

## Recursos do MVP

- Importação de currículo em PDF, DOCX ou TXT.
- Extração e prévia do texto do currículo.
- Cadastro manual de vagas.
- Caça de vagas com IA a partir do currículo em portais de emprego.
- Importação de vagas demo.
- Classificação automática do canal da vaga.
- Análise de compatibilidade com IA via OpenRouter.
- Geração de recomendação e carta curta de apresentação.
- Criação de candidaturas e histórico local.
- Envio automático de e-mail apenas para vagas com e-mail direto legítimo.
- Bloqueio de envio para LinkedIn, Indeed, Gupy, InfoJobs, Glassdoor, Catho, Vagas.com, Remotar, Programathor, Trampos, GeekHunter e plataformas parecidas.
- Interface Windows nativa com PySide6, Qt Widgets, `QMainWindow` e `QStackedWidget`.

## Radar de vagas por portais

Na página "Vagas", use o botão "Acelerar radar".

O fluxo é:

1. O app usa o currículo principal, preferencialmente já estruturado com IA.
2. O radar cria buscas direcionadas para LinkedIn, InfoJobs, Gupy, Indeed, Vagas.com, Catho, Glassdoor, Remotar, Programathor e Trampos.
3. O app consulta resultados públicos de busca com `site:` para esses portais.
4. Cada resultado passa por filtros de vaga real, área, modalidade e compatibilidade com o currículo.
5. A IA avalia cargo, tecnologias, nível e preferências antes de salvar.
6. Apenas vagas com compatibilidade suficiente entram no banco local.
7. Links de plataformas de emprego entram como `sensitive_platform` para candidatura manual.
8. Sites institucionais fora de plataformas sensíveis podem passar por uma busca leve de e-mail público na própria página.
9. Se um e-mail direto for encontrado, a vaga entra como `email_auto`.

O app não faz login, não burla captcha, não usa Selenium e não envia candidatura em plataformas sensíveis.

## Instalação

Use Python 3.14.5 ou versão compatível instalada no Windows.

```powershell
pip install -r requirements.txt
```

## Configurar OpenRouter

Crie a variável de ambiente global:

```powershell
setx OPENROUTER_API_KEY "sua_chave_openrouter"
```

O app usa:

```python
base_url = "https://openrouter.ai/api/v1"
```

Modelo padrão:

```text
openai/gpt-4o-mini
```

Opcionalmente, defina:

```powershell
setx OPENROUTER_MODEL "openai/gpt-4o-mini"
```

## Configurar SMTP

Para envio de candidaturas por e-mail, configure:

```powershell
setx SMTP_HOST "smtp.example.com"
setx SMTP_PORT "587"
setx SMTP_USER "usuario@example.com"
setx SMTP_PASSWORD "senha"
setx FROM_EMAIL "usuario@example.com"
```

Também é possível copiar `.env.example` para `.env` durante testes locais.

## Rodar o app

```powershell
python main.py
```

Ao iniciar, o app cria automaticamente:

- `data/`
- `data/resumes/`
- `data/careerpilot.db`

## Gerar executável

```powershell
pyinstaller --noconfirm --onefile --windowed --name CareerPilotAI main.py
```

O executável será gerado na pasta `dist/`.

## Canais de vaga

`email_auto`

Vagas com e-mail direto de RH ou empresa. O app pode preparar e enviar e-mail automaticamente com o currículo anexado, desde que SMTP esteja configurado.

`sensitive_platform`

Vagas de LinkedIn, Indeed, Gupy, InfoJobs, Glassdoor, Catho, Vagas.com, Remotar, Programathor, Trampos, GeekHunter ou plataformas parecidas. O app mostra link, score, resumo e recomendação manual. O botão permitido é "Abrir link". Não há clique automático, preenchimento automático, Selenium ou tentativa de burlar regras.

`manual_review`

Vagas sem e-mail direto e fora de plataformas sensíveis. Ficam aguardando revisão manual antes de qualquer ação.

## Segurança e ética

O CareerPilot AI não deve:

- Burlar plataformas.
- Automatizar candidatura em LinkedIn, Indeed, Gupy, InfoJobs, Glassdoor, Catho, Vagas.com, Remotar, Programathor, Trampos, GeekHunter ou similares.
- Burlar captcha.
- Simular comportamento humano em navegador.
- Usar Selenium para candidatura.
- Fazer scraping agressivo.
- Inventar experiências no currículo.
- Criar habilidades falsas.

O envio automático é permitido somente quando houver e-mail direto e legítimo da empresa ou RH.

## Testar com vagas demo

1. Abra o app.
2. Importe um currículo em PDF, DOCX ou TXT.
3. Vá para "Vagas".
4. Clique em "Importar vagas demo".
5. Selecione uma vaga.
6. Clique em "Analisar com IA".
7. Veja a análise em "Análises".
8. Crie uma candidatura.
9. Em "Candidaturas", envie e-mail apenas para vagas `email_auto` ou abra o link manualmente para `sensitive_platform`.
