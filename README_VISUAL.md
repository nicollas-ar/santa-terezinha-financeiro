# Redesign visual 4.0 — Santa Terezinha do Menino Jesus

Esta atualização mantém o app.py, modelos, rotas, formulários e permissões da versão personalizada anterior. Mudanças em templates/base.html, templates/analytics.html e static/style.css.

## Publicar
1. Faça backup do repositório e do banco antes de alterar.
2. Copie os arquivos deste projeto sobre os arquivos correspondentes no repositório GitHub.
3. Não envie `.env` nem arquivos `.db` ao GitHub.
4. Faça commit/push; aguarde o deploy do Render.
5. Recarregue a página com Ctrl+F5 para atualizar o CSS.

Nenhuma migração do banco é necessária. A interface de dashboards usa Chart.js por CDN e as fontes Google Fonts (necessitam internet). Teste o login, o perfil de secretaria e a aprovação de lançamentos após o deploy.