/**
 * Tests unitaires pour sock_helpers.
 * Exécution : node --test tests/sock_helpers.test.js
 *
 * Couvre :
 *   - sendTextWithPause : ordre presence → message, contenu texte exact
 *   - sendAudioBuffer   : séquence recording → delay → paused → audio
 *   - AUDIO_MIMETYPE    : contrat de la constante migrée
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert");
const {
    sendTextWithPause,
    sendAudioBuffer,
    AUDIO_MIMETYPE,
} = require("../lib/sock_helpers");

function makeSockMock() {
    const sent = [];
    const presence = [];
    return {
        sent,
        presence,
        sendMessage: async (num, msg) => { sent.push({ num, msg }); },
        sendPresenceUpdate: async (state, num) => { presence.push({ state, num }); },
    };
}

describe("sock_helpers — sendTextWithPause", () => {
    test("envoie sendPresenceUpdate('paused') puis sendMessage avec le texte", async () => {
        const sock = makeSockMock();
        await sendTextWithPause(sock, "user-1@s.w.net", "Bonjour");
        assert.strictEqual(sock.presence.length, 1);
        assert.strictEqual(sock.presence[0].state, "paused");
        assert.strictEqual(sock.presence[0].num, "user-1@s.w.net");
        assert.strictEqual(sock.sent.length, 1);
        assert.deepStrictEqual(sock.sent[0].msg, { text: "Bonjour" });
        assert.strictEqual(sock.sent[0].num, "user-1@s.w.net");
    });

    test("préserve un texte vide (cas limite acceptable)", async () => {
        const sock = makeSockMock();
        await sendTextWithPause(sock, "u1", "");
        assert.strictEqual(sock.presence.length, 1);
        assert.deepStrictEqual(sock.sent[0].msg, { text: "" });
    });

    test("préserve un texte avec caractères dioula (UTF-8)", async () => {
        const sock = makeSockMock();
        await sendTextWithPause(sock, "u1", "Aw ni sɔgɔma! N tɔgɔ ye Wourri ye.");
        assert.strictEqual(sock.sent[0].msg.text, "Aw ni sɔgɔma! N tɔgɔ ye Wourri ye.");
    });
});

describe("sock_helpers — sendAudioBuffer", () => {
    test("séquence ordonnée : recording → delay → paused → sendMessage", async () => {
        const sock = makeSockMock();
        const delayCalls = [];
        const buffer = Buffer.from("fake-audio-bytes");
        await sendAudioBuffer(sock, "u1", buffer, {
            randomDelay: async (min, max) => { delayCalls.push({ min, max }); },
        });

        // Ordre vérifié via le tableau presence (recording avant paused)
        assert.strictEqual(sock.presence.length, 2);
        assert.strictEqual(sock.presence[0].state, "recording");
        assert.strictEqual(sock.presence[1].state, "paused");
        // delay invoqué une fois avec (1000, 2000)
        assert.strictEqual(delayCalls.length, 1);
        assert.deepStrictEqual(delayCalls[0], { min: 1000, max: 2000 });
        // sendMessage avec le buffer + mimetype + ptt
        assert.strictEqual(sock.sent.length, 1);
        assert.strictEqual(sock.sent[0].msg.audio, buffer);
        assert.strictEqual(sock.sent[0].msg.mimetype, AUDIO_MIMETYPE);
        assert.strictEqual(sock.sent[0].msg.ptt, true);
    });

    test("userNumber propagé aux 3 appels sock", async () => {
        const sock = makeSockMock();
        await sendAudioBuffer(sock, "u-special@s.w.net", Buffer.from("x"), {
            randomDelay: async () => {},
        });
        assert.strictEqual(sock.presence[0].num, "u-special@s.w.net");
        assert.strictEqual(sock.presence[1].num, "u-special@s.w.net");
        assert.strictEqual(sock.sent[0].num, "u-special@s.w.net");
    });

    test("randomDelay appelé entre les 2 presence updates (pas avant, pas après sendMessage)", async () => {
        const sock = makeSockMock();
        const trace = [];
        // Remplacer sock pour tracer chaque appel dans l'ordre
        const tracedSock = {
            sendPresenceUpdate: async (state, num) => { trace.push(`presence:${state}`); },
            sendMessage: async (num, msg) => { trace.push("sendMessage"); },
        };
        await sendAudioBuffer(tracedSock, "u1", Buffer.from("x"), {
            randomDelay: async () => { trace.push("delay"); },
        });
        assert.deepStrictEqual(trace, [
            "presence:recording",
            "delay",
            "presence:paused",
            "sendMessage",
        ]);
    });

    test("buffer audio préservé tel quel (pas de copie ni conversion)", async () => {
        const sock = makeSockMock();
        const buffer = Buffer.from([0xFF, 0xFB, 0x90, 0x44]); // bytes arbitraires
        await sendAudioBuffer(sock, "u1", buffer, { randomDelay: async () => {} });
        assert.strictEqual(sock.sent[0].msg.audio, buffer); // même référence
    });
});

describe("sock_helpers — exports", () => {
    test("AUDIO_MIMETYPE === 'audio/ogg; codecs=opus' (contrat constante migrée)", () => {
        assert.strictEqual(AUDIO_MIMETYPE, "audio/ogg; codecs=opus");
    });

    test("sendTextWithPause et sendAudioBuffer sont des fonctions async", () => {
        assert.strictEqual(typeof sendTextWithPause, "function");
        assert.strictEqual(typeof sendAudioBuffer, "function");
        // async functions ont une signature `AsyncFunction`
        assert.strictEqual(sendTextWithPause.constructor.name, "AsyncFunction");
        assert.strictEqual(sendAudioBuffer.constructor.name, "AsyncFunction");
    });
});
