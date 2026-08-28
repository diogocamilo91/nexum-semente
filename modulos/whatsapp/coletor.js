/* ===========================================================================
 * COLETOR DO WHATSAPP — espelho SÓ-LEITURA (kit NEXUM Semente)
 *
 * A VPS entra como mais um "aparelho conectado" (igual ao WhatsApp Web) e vai
 * guardando uma cópia das mensagens em disco. NADA aqui escreve no WhatsApp:
 * não envia, não marca como lido, não aparece online, não baixa mídia.
 *
 * A trava é objetiva: o instalador procura neste arquivo QUALQUER chamada de
 * envio, de marcar-como-lido, de presença ou de alterar conversa/perfil — e a
 * busca tem que voltar VAZIA. (A lista dos nomes procurados mora no instalar.sh,
 * de propósito: escrevê-la aqui faria o próprio comentário disparar o alarme.)
 *
 * Escreve, dentro de ~/semente-whatsapp/ (fora da pasta de conhecimento, logo
 * fora do backup — conversa de terceiro não sai da máquina):
 *     dados/mensagens.jsonl   {ts, chat, chatNome, de, deNome, texto, tipo}
 *     dados/chats.json        {"<id>": "<nome>"}
 *     dados/contatos.json     {"<id>": "<nome>"}
 *     qr.png                  só enquanto espera o pareamento
 *
 * Uso:  node coletor.js            liga o espelho
 *       node coletor.js --autoteste  prova o caminho de gravação sem WhatsApp
 * =========================================================================== */
'use strict'

const fs = require('fs')
const path = require('path')

const BASE = __dirname
const DADOS = path.join(BASE, 'dados')
const AUTH = path.join(BASE, 'auth')
const LOGS = path.join(BASE, 'logs')
const ARQ_MSGS = path.join(DADOS, 'mensagens.jsonl')
const ARQ_CHATS = path.join(DADOS, 'chats.json')
const ARQ_CONTATOS = path.join(DADOS, 'contatos.json')
const ARQ_QR = path.join(BASE, 'qr.png')

for (const d of [DADOS, AUTH, LOGS]) fs.mkdirSync(d, { recursive: true })
try { fs.chmodSync(AUTH, 0o700) } catch (e) {}

function log (msg) {
  const linha = new Date().toISOString().replace('T', ' ').slice(0, 19) + '  ' + msg
  console.log(linha)
}

/* ------------------------------------------------------------------ mapas */
function lerMapa (arq) {
  try { return JSON.parse(fs.readFileSync(arq, 'utf8')) } catch (e) { return {} }
}
/* escrita atômica: disco cheio no meio de um write zera o arquivo calado */
function gravarMapa (arq, obj) {
  try {
    const tmp = arq + '.tmp'
    fs.writeFileSync(tmp, JSON.stringify(obj, null, 1))
    fs.renameSync(tmp, arq)
  } catch (e) { log('não consegui gravar ' + path.basename(arq) + ': ' + e.message) }
}

const chats = lerMapa(ARQ_CHATS)
const contatos = lerMapa(ARQ_CONTATOS)
let mapaSujo = false

function guardarNome (mapa, id, nome) {
  if (!id || !nome) return
  nome = String(nome).trim()
  if (!nome || nome === id) return
  if (mapa[id] === nome) return
  mapa[id] = nome
  mapaSujo = true
}

setInterval(() => {
  if (!mapaSujo) return
  mapaSujo = false
  gravarMapa(ARQ_CHATS, chats)
  gravarMapa(ARQ_CONTATOS, contatos)
}, 15000).unref?.()

/* --------------------------------------------------------------- mensagem */
const TIPOS_AMIGAVEIS = {
  imageMessage: '[imagem]', videoMessage: '[vídeo]', audioMessage: '[áudio]',
  documentMessage: '[documento]', stickerMessage: '[figurinha]',
  locationMessage: '[localização]', contactMessage: '[contato]',
  contactsArrayMessage: '[contatos]', pollCreationMessage: '[enquete]',
  reactionMessage: '[reação]', ptvMessage: '[vídeo]'
}

/** Extrai o miolo da mensagem, atravessando os embrulhos do protocolo. */
function desembrulhar (m) {
  let atual = m
  for (let i = 0; i < 5 && atual; i++) {
    if (atual.ephemeralMessage) { atual = atual.ephemeralMessage.message; continue }
    if (atual.viewOnceMessage) { atual = atual.viewOnceMessage.message; continue }
    if (atual.viewOnceMessageV2) { atual = atual.viewOnceMessageV2.message; continue }
    if (atual.documentWithCaptionMessage) {
      atual = atual.documentWithCaptionMessage.message; continue
    }
    break
  }
  return atual || {}
}

/** Devolve {texto, tipo} de uma mensagem. Mídia entra só como MARCA. */
function lerConteudo (message) {
  const m = desembrulhar(message)
  if (!m || typeof m !== 'object') return { texto: '', tipo: 'desconhecido' }
  if (typeof m.conversation === 'string') {
    return { texto: m.conversation, tipo: 'conversation' }
  }
  if (m.extendedTextMessage && typeof m.extendedTextMessage.text === 'string') {
    return { texto: m.extendedTextMessage.text, tipo: 'conversation' }
  }
  for (const chave of Object.keys(TIPOS_AMIGAVEIS)) {
    if (m[chave]) {
      const legenda = (m[chave] && typeof m[chave].caption === 'string') ? m[chave].caption : ''
      return { texto: (TIPOS_AMIGAVEIS[chave] + (legenda ? ' ' + legenda : '')).trim(), tipo: chave }
    }
  }
  const primeiro = Object.keys(m)[0] || 'desconhecido'
  return { texto: '', tipo: primeiro }
}

function soNumero (jid) {
  return String(jid || '').split(':')[0].split('@')[0]
}

/** Uma mensagem do protocolo vira a linha que a tela do app sabe ler. */
function normalizar (msg) {
  if (!msg || !msg.key || !msg.message) return null
  const chat = msg.key.remoteJid || ''
  if (!chat || chat === 'status@broadcast') return null       // "status" não é conversa
  const grupo = chat.endsWith('@g.us')
  const deMim = !!msg.key.fromMe
  const autor = deMim ? 'eu' : (grupo ? (msg.key.participant || '') : chat)
  const { texto, tipo } = lerConteudo(msg.message)
  const ts = Number(msg.messageTimestamp && msg.messageTimestamp.low != null
    ? msg.messageTimestamp.low : msg.messageTimestamp) || Math.floor(Date.now() / 1000)
  const deNome = deMim ? 'Você'
    : (contatos[autor] || msg.pushName || soNumero(autor) || '')
  return {
    ts,
    chat,
    chatNome: chats[chat] || (grupo ? '' : (contatos[chat] || msg.pushName || soNumero(chat))),
    de: deMim ? 'eu' : autor,
    deNome,
    texto,
    tipo,
    fromMe: deMim
  }
}

/* Evita gravar duas vezes a mesma mensagem (o histórico chega junto com o vivo). */
const vistas = new Set()
function jaVi (msg) {
  const id = (msg.key && msg.key.id) || ''
  if (!id) return false
  if (vistas.has(id)) return true
  vistas.add(id)
  if (vistas.size > 20000) {                 // não crescer pra sempre na memória
    for (const v of vistas) { vistas.delete(v); if (vistas.size <= 15000) break }
  }
  return false
}

function gravar (msgs, origem) {
  let n = 0
  let bloco = ''
  for (const msg of msgs || []) {
    try {
      if (jaVi(msg)) continue
      const linha = normalizar(msg)
      if (!linha) continue
      if (!linha.fromMe && msg.pushName) {
        guardarNome(contatos, linha.de, msg.pushName)
      }
      bloco += JSON.stringify(linha) + '\n'
      n++
    } catch (e) { /* uma mensagem estranha nunca derruba o espelho */ }
  }
  if (!bloco) return 0
  try { fs.appendFileSync(ARQ_MSGS, bloco) } catch (e) {
    log('não consegui gravar mensagem: ' + e.message)
    return 0
  }
  if (origem) log(origem + ': +' + n + ' mensagem(ns)')
  return n
}

function registrarChats (lista) {
  for (const c of lista || []) {
    guardarNome(chats, c.id, c.name || c.subject || (c.conversationTimestamp ? '' : ''))
  }
}
function registrarContatos (lista) {
  for (const c of lista || []) guardarNome(contatos, c.id, c.name || c.notify || c.verifiedName)
}

/* ------------------------------------------------------- prova sem WhatsApp
 * Roda o MESMO caminho de gravação com uma mensagem inventada e confere que a
 * linha saiu no formato que a tela do app lê. É o que deixa o instalador provar
 * a metade que não depende de parear o celular. */
function autoteste () {
  const fingido = {
    key: { remoteJid: '5500000000000@s.whatsapp.net', id: 'PROVA' + Date.now(), fromMe: false },
    pushName: 'Teste da Instalação',
    messageTimestamp: Math.floor(Date.now() / 1000),
    message: { conversation: 'mensagem de prova da instalação' }
  }
  const fingidoMidia = {
    key: { remoteJid: '5500000000001@g.us', id: 'PROVAM' + Date.now(), fromMe: false,
      participant: '5500000000002@s.whatsapp.net' },
    pushName: 'Fulano da Prova',
    messageTimestamp: Math.floor(Date.now() / 1000),
    message: { imageMessage: { caption: 'olha a foto', mimetype: 'image/jpeg' } }
  }
  const antes = fs.existsSync(ARQ_MSGS) ? fs.statSync(ARQ_MSGS).size : 0
  const n = gravar([fingido, fingidoMidia], null)
  if (n !== 2) { console.error('PROVA FALHOU: gravou ' + n + ' de 2'); process.exit(1) }
  const novas = fs.readFileSync(ARQ_MSGS, 'utf8').slice(antes).trim().split('\n')
  const obrigatorios = ['ts', 'chat', 'chatNome', 'de', 'deNome', 'texto', 'tipo']
  for (const linha of novas) {
    const o = JSON.parse(linha)
    for (const campo of obrigatorios) {
      if (!(campo in o)) { console.error('PROVA FALHOU: falta o campo ' + campo); process.exit(1) }
    }
  }
  const midia = JSON.parse(novas[1])
  if (midia.tipo !== 'imageMessage' || !midia.texto.startsWith('[imagem]')) {
    console.error('PROVA FALHOU: mídia não virou marca — saiu ' + JSON.stringify(midia))
    process.exit(1)
  }
  if (midia.texto.includes('mimetype') || JSON.stringify(midia).includes('jpeg')) {
    console.error('PROVA FALHOU: o arquivo da mídia vazou pro registro'); process.exit(1)
  }
  gravarMapa(ARQ_CHATS, chats)
  gravarMapa(ARQ_CONTATOS, contatos)
  console.log('PROVA OK: 2 linhas no formato que a tela lê, mídia só como marca')
  process.exit(0)
}

/* ------------------------------------------------------------------ ligação */
async function ligar () {
  const baileys = require('baileys')
  const makeWASocket = baileys.default || baileys.makeWASocket
  const { useMultiFileAuthState, fetchLatestBaileysVersion, DisconnectReason } = baileys
  const pino = require('pino')
  const QRCode = require('qrcode')

  const logger = pino({ level: 'silent' })
  const { state, saveCreds } = await useMultiFileAuthState(AUTH)
  const { version } = await fetchLatestBaileysVersion()
  log('ligando o espelho (protocolo ' + version.join('.') + ')')

  const auth = baileys.makeCacheableSignalKeyStore
    ? { creds: state.creds, keys: baileys.makeCacheableSignalKeyStore(state.keys, logger) }
    : state

  const sock = makeWASocket({
    version,
    logger,
    auth,
    printQRInTerminal: false,      // o QR vira arquivo: a pessoa não tem terminal aberto
    markOnlineOnConnect: false,    // TRAVA: não aparece online, não rouba a notificação do celular
    syncFullHistory: false,        // o histórico inteiro não cabe numa VPS pequena
    browser: ['Assistente', 'Chrome', '1.0']
  })

  sock.ev.on('creds.update', saveCreds)

  let espera = 0
  let reconectando = false

  sock.ev.on('connection.update', (u) => {
    const { connection, lastDisconnect, qr } = u
    if (qr) {
      QRCode.toFile(ARQ_QR, qr, { scale: 8 })
        .then(() => log('QR pronto em qr.png — leia pelo celular em Aparelhos conectados'))
        .catch((e) => log('não consegui gravar o QR: ' + e.message))
    }
    if (connection === 'open') {
      espera = 0
      log('CONECTADO — o espelho está de pé (só leitura)')
      try { if (fs.existsSync(ARQ_QR)) fs.unlinkSync(ARQ_QR) } catch (e) {}
    }
    if (connection === 'close') {
      const code = lastDisconnect && lastDisconnect.error && lastDisconnect.error.output
        ? lastDisconnect.error.output.statusCode : 0
      if (code === DisconnectReason.loggedOut) {
        log('DESLOGADO: o aparelho foi removido no celular. Pare o espelho, apague a pasta auth/ e pareie de novo.')
        return
      }
      if (reconectando) return
      reconectando = true
      // Espera CRESCENTE. Martelar de 5 em 5s quando o WhatsApp está recusando é
      // o que arrisca bloquear o número — nunca troque isto por um intervalo fixo.
      espera = Math.min(espera ? espera * 2 : 5000, 120000)
      log('a ligação caiu (código ' + code + ') — tentando de novo em ' + Math.round(espera / 1000) + 's')
      setTimeout(() => {
        reconectando = false
        ligar().catch((e) => log('erro ao religar: ' + e.message))
      }, espera)
    }
  })

  sock.ev.on('messages.upsert', (ev) => gravar(ev.messages, 'agora'))
  sock.ev.on('messaging-history.set', (ev) => {
    registrarContatos(ev.contacts)
    registrarChats(ev.chats)
    gravar(ev.messages, 'histórico')
  })
  sock.ev.on('chats.upsert', registrarChats)
  sock.ev.on('chats.update', registrarChats)
  sock.ev.on('contacts.upsert', registrarContatos)
  sock.ev.on('contacts.update', registrarContatos)
}

function sair () {
  if (mapaSujo) { gravarMapa(ARQ_CHATS, chats); gravarMapa(ARQ_CONTATOS, contatos) }
  process.exit(0)
}
process.on('SIGTERM', sair)
process.on('SIGINT', sair)

if (process.argv.includes('--autoteste')) autoteste()
else ligar().catch((e) => { log('não consegui ligar: ' + e.message); process.exit(1) })
