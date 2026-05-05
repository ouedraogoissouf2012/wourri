/**
 * Tests unitaires pour MessageQueue.
 * Exécution : node --test tests/message_queue.test.js
 */
"use strict";

const { test, describe, beforeEach, afterEach } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { MessageQueue } = require("../lib/message_queue");

const silentLogger = { log: () => {}, error: () => {} };

describe("MessageQueue — load et persistence basique", () => {
    let tmpDir;
    let filePath;

    beforeEach(() => {
        tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "queue-test-"));
        filePath = path.join(tmpDir, "queue.json");
    });

    afterEach(() => {
        try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch (_) {}
    });

    test("load() sur fichier inexistant retourne 0 messages", async () => {
        const q = new MessageQueue({ filePath, logger: silentLogger });
        const n = await q.load();
        assert.strictEqual(n, 0);
        assert.strictEqual(q.stats.total, 0);
        assert.strictEqual(q.stats.loaded, true);
    });

    test("constructor sans filePath jette une erreur", () => {
        assert.throws(
            () => new MessageQueue({ logger: silentLogger }),
            /filePath requis/
        );
    });

    test("fichier corrompu : ne crash pas, queue vide", async () => {
        fs.writeFileSync(filePath, "{ ceci n'est pas du JSON valide", "utf-8");
        const q = new MessageQueue({ filePath, logger: silentLogger });
        const n = await q.load();
        assert.strictEqual(n, 0);
    });

    test("fichier vide : ne crash pas, queue vide", async () => {
        fs.writeFileSync(filePath, "", "utf-8");
        const q = new MessageQueue({ filePath, logger: silentLogger });
        const n = await q.load();
        assert.strictEqual(n, 0);
    });
});

describe("MessageQueue — add", () => {
    let tmpDir;
    let filePath;

    beforeEach(() => {
        tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "queue-test-"));
        filePath = path.join(tmpDir, "queue.json");
    });

    afterEach(() => {
        try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch (_) {}
    });

    test("add() ajoute un message et le persiste", async () => {
        const q = new MessageQueue({ filePath, logger: silentLogger });
        await q.load();
        const added = await q.add({
            id: "wamsg_1",
            userNumber: "22541540178@s.whatsapp.net",
            payload: { text: "hello" },
        });
        assert.strictEqual(added, true);
        assert.strictEqual(q.stats.total, 1);

        // Vérifier persistence
        const q2 = new MessageQueue({ filePath, logger: silentLogger });
        await q2.load();
        assert.strictEqual(q2.stats.total, 1);
        const pending = q2.getPending();
        assert.strictEqual(pending[0].id, "wamsg_1");
        assert.strictEqual(pending[0].payload.text, "hello");
    });

    test("add() est idempotent sur id (pas de duplicate)", async () => {
        const q = new MessageQueue({ filePath, logger: silentLogger });
        await q.load();
        await q.add({ id: "wamsg_1", userNumber: "u1", payload: {} });
        const added2 = await q.add({ id: "wamsg_1", userNumber: "u1", payload: {} });
        assert.strictEqual(added2, false);
        assert.strictEqual(q.stats.total, 1);
    });

    test("add() sans id throws", async () => {
        const q = new MessageQueue({ filePath, logger: silentLogger });
        await q.load();
        await assert.rejects(
            () => q.add({ userNumber: "u1", payload: {} }),
            /msg.id is required/
        );
    });

    test("add() ajoute timestamps et attemptCount initial", async () => {
        const q = new MessageQueue({ filePath, logger: silentLogger });
        await q.load();
        await q.add({ id: "wamsg_1", userNumber: "u1", payload: {} });
        const pending = q.getPending();
        assert.ok(pending[0].createdAt);
        assert.strictEqual(pending[0].attemptCount, 0);
        assert.strictEqual(pending[0].lastError, null);
        assert.strictEqual(pending[0].lastAttemptAt, null);
    });
});

describe("MessageQueue — markSuccess et markFailure", () => {
    let tmpDir;
    let filePath;

    beforeEach(() => {
        tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "queue-test-"));
        filePath = path.join(tmpDir, "queue.json");
    });

    afterEach(() => {
        try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch (_) {}
    });

    test("markSuccess() retire le message de la queue", async () => {
        const q = new MessageQueue({ filePath, logger: silentLogger });
        await q.load();
        await q.add({ id: "wamsg_1", userNumber: "u1", payload: {} });
        const removed = await q.markSuccess("wamsg_1");
        assert.strictEqual(removed, true);
        assert.strictEqual(q.stats.total, 0);
    });

    test("markSuccess() retourne false si id inconnu", async () => {
        const q = new MessageQueue({ filePath, logger: silentLogger });
        await q.load();
        const removed = await q.markSuccess("unknown");
        assert.strictEqual(removed, false);
    });

    test("markFailure() incrémente attemptCount et garde le message", async () => {
        const q = new MessageQueue({ filePath, logger: silentLogger });
        await q.load();
        await q.add({ id: "wamsg_1", userNumber: "u1", payload: {} });
        await q.markFailure("wamsg_1", new Error("API down"));
        await q.markFailure("wamsg_1", new Error("API still down"));

        const pending = q.getPending();
        assert.strictEqual(pending.length, 1);
        assert.strictEqual(pending[0].attemptCount, 2);
        assert.match(pending[0].lastError, /API still down/);
        assert.ok(pending[0].lastAttemptAt);
    });

    test("markFailure() avec string error fonctionne", async () => {
        const q = new MessageQueue({ filePath, logger: silentLogger });
        await q.load();
        await q.add({ id: "wamsg_1", userNumber: "u1", payload: {} });
        await q.markFailure("wamsg_1", "timeout");
        assert.strictEqual(q.getPending()[0].lastError, "timeout");
    });

    test("markFailure() retourne false si id inconnu", async () => {
        const q = new MessageQueue({ filePath, logger: silentLogger });
        await q.load();
        const r = await q.markFailure("unknown", new Error("x"));
        assert.strictEqual(r, false);
    });
});

describe("MessageQueue — getPending et getDead", () => {
    let tmpDir;
    let filePath;

    beforeEach(() => {
        tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "queue-test-"));
        filePath = path.join(tmpDir, "queue.json");
    });

    afterEach(() => {
        try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch (_) {}
    });

    test("getPending() exclut les messages morts (attemptCount >= maxAttempts)", async () => {
        const q = new MessageQueue({
            filePath,
            maxAttempts: 3,
            logger: silentLogger,
        });
        await q.load();
        await q.add({ id: "m1", userNumber: "u1", payload: {} });
        await q.add({ id: "m2", userNumber: "u1", payload: {} });
        for (let i = 0; i < 3; i++) {
            await q.markFailure("m1", new Error("x"));
        }
        // m1 atteint maxAttempts → mort
        assert.strictEqual(q.getPending().length, 1);
        assert.strictEqual(q.getPending()[0].id, "m2");
        assert.strictEqual(q.getDead().length, 1);
        assert.strictEqual(q.getDead()[0].id, "m1");
        assert.strictEqual(q.stats.dead, 1);
        assert.strictEqual(q.stats.pending, 1);
    });

    test("getPending({ limit }) respecte limit", async () => {
        const q = new MessageQueue({ filePath, logger: silentLogger });
        await q.load();
        for (let i = 0; i < 5; i++) {
            await q.add({ id: `m${i}`, userNumber: "u1", payload: {} });
        }
        const pending = q.getPending({ limit: 2 });
        assert.strictEqual(pending.length, 2);
    });

    test("getPending() retourne une copie (modification externe sans effet)", async () => {
        const q = new MessageQueue({ filePath, logger: silentLogger });
        await q.load();
        await q.add({ id: "m1", userNumber: "u1", payload: { a: 1 } });
        const pending = q.getPending();
        pending[0].payload.a = 999;
        const reread = q.getPending();
        assert.strictEqual(reread[0].payload.a, 999); // shallow copy : payload référence partagée
        // mais le tableau lui-même est une copie : pas d'effet de push externe
        pending.push({ id: "fake" });
        assert.strictEqual(q.getPending().length, 1);
    });
});

describe("MessageQueue — persistence après simulation de kill", () => {
    let tmpDir;
    let filePath;

    beforeEach(() => {
        tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "queue-test-"));
        filePath = path.join(tmpDir, "queue.json");
    });

    afterEach(() => {
        try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch (_) {}
    });

    test("3 messages survivent à un redémarrage simulé", async () => {
        const q1 = new MessageQueue({ filePath, logger: silentLogger });
        await q1.load();
        for (let i = 0; i < 3; i++) {
            await q1.add({ id: `m${i}`, userNumber: "u1", payload: { idx: i } });
        }
        await q1.markFailure("m0", new Error("first failure"));

        // Nouveau process simulé
        const q2 = new MessageQueue({ filePath, logger: silentLogger });
        await q2.load();
        assert.strictEqual(q2.stats.total, 3);

        const pending = q2.getPending();
        assert.strictEqual(pending.length, 3);
        const m0 = pending.find((m) => m.id === "m0");
        assert.strictEqual(m0.attemptCount, 1);
        assert.match(m0.lastError, /first failure/);

        // Une success sur le nouveau process se persiste
        await q2.markSuccess("m1");
        const q3 = new MessageQueue({ filePath, logger: silentLogger });
        await q3.load();
        assert.strictEqual(q3.stats.total, 2);
        assert.ok(!q3.getPending().find((m) => m.id === "m1"));
    });
});

describe("MessageQueue — sérialisation des writes (anti-race)", () => {
    let tmpDir;
    let filePath;

    beforeEach(() => {
        tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "queue-test-"));
        filePath = path.join(tmpDir, "queue.json");
    });

    afterEach(() => {
        try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch (_) {}
    });

    test("Promise.all sur 10 add() en parallèle : tous persistés", async () => {
        const q = new MessageQueue({ filePath, logger: silentLogger });
        await q.load();

        await Promise.all(
            Array.from({ length: 10 }, (_, i) =>
                q.add({ id: `m${i}`, userNumber: "u1", payload: { idx: i } })
            )
        );

        assert.strictEqual(q.stats.total, 10);

        // Vérifier persistence
        const q2 = new MessageQueue({ filePath, logger: silentLogger });
        await q2.load();
        assert.strictEqual(q2.stats.total, 10);
    });
});
