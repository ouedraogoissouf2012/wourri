/**
 * Tests unitaires pour lib/logger.js
 * Exécution : node --test tests/logger.test.js
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert");
const { Writable } = require("node:stream");
const { createLogger } = require("../lib/logger");

/** Stream qui capture les logs JSON pour assertions */
function makeCaptureStream() {
    const lines = [];
    const stream = new Writable({
        write(chunk, _enc, cb) {
            lines.push(chunk.toString());
            cb();
        },
    });
    stream.lines = lines;
    return stream;
}

/** Parse les lignes JSON capturées (filtre les vides) */
function parseLines(lines) {
    return lines
        .join("")
        .split("\n")
        .filter(Boolean)
        .map((l) => {
            try { return JSON.parse(l); } catch { return null; }
        })
        .filter(Boolean);
}

describe("logger — niveau et format", () => {
    test("default level = info", () => {
        const stream = makeCaptureStream();
        const logger = createLogger({ forceJson: true, destination: stream });
        logger.debug("debug-message"); // ne devrait pas être loggé
        logger.info("info-message");
        const events = parseLines(stream.lines);
        assert.strictEqual(events.length, 1);
        assert.strictEqual(events[0].msg, "info-message");
    });

    test("level configurable", () => {
        const stream = makeCaptureStream();
        const logger = createLogger({ level: "debug", forceJson: true, destination: stream });
        logger.debug("debug-message");
        logger.info("info-message");
        const events = parseLines(stream.lines);
        assert.strictEqual(events.length, 2);
    });

    test("level invalide → fallback info", () => {
        const stream = makeCaptureStream();
        const logger = createLogger({ level: "FOOBAR", forceJson: true, destination: stream });
        logger.info("ok");
        const events = parseLines(stream.lines);
        assert.strictEqual(events.length, 1);
    });

    test("base field 'service' présent", () => {
        const stream = makeCaptureStream();
        const logger = createLogger({ forceJson: true, destination: stream });
        logger.info("hello");
        const events = parseLines(stream.lines);
        assert.strictEqual(events[0].service, "wouri-whatsapp");
    });

    test("timestamp ISO présent", () => {
        const stream = makeCaptureStream();
        const logger = createLogger({ forceJson: true, destination: stream });
        logger.info("hello");
        const events = parseLines(stream.lines);
        assert.match(events[0].time, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
    });

    test("contexte structuré dans la première arg", () => {
        const stream = makeCaptureStream();
        const logger = createLogger({ forceJson: true, destination: stream });
        logger.info({ userNumber: "u1", queueId: "m1" }, "[QUEUE] add");
        const events = parseLines(stream.lines);
        assert.strictEqual(events[0].userNumber, "u1");
        assert.strictEqual(events[0].queueId, "m1");
        assert.strictEqual(events[0].msg, "[QUEUE] add");
    });

    test("error avec err object sérialise correctement", () => {
        const stream = makeCaptureStream();
        const logger = createLogger({ forceJson: true, destination: stream });
        const err = new Error("boom");
        logger.error({ err }, "Erreur");
        const events = parseLines(stream.lines);
        assert.strictEqual(events[0].err.type, "Error");
        assert.strictEqual(events[0].err.message, "boom");
        assert.ok(events[0].err.stack);
    });
});

describe("logger — niveaux silencieux", () => {
    test("silent ne log rien", () => {
        const stream = makeCaptureStream();
        const logger = createLogger({ level: "silent", forceJson: true, destination: stream });
        logger.fatal("rien");
        logger.error("rien");
        logger.info("rien");
        const events = parseLines(stream.lines);
        assert.strictEqual(events.length, 0);
    });

    test("warn level filtre info et debug", () => {
        const stream = makeCaptureStream();
        const logger = createLogger({ level: "warn", forceJson: true, destination: stream });
        logger.debug("d");
        logger.info("i");
        logger.warn("w");
        logger.error("e");
        const events = parseLines(stream.lines);
        assert.strictEqual(events.length, 2);
        assert.deepStrictEqual(events.map((e) => e.msg), ["w", "e"]);
    });
});

describe("logger — child loggers", () => {
    test("child() hérite du contexte", () => {
        const stream = makeCaptureStream();
        const logger = createLogger({ forceJson: true, destination: stream });
        const child = logger.child({ component: "test" });
        child.info("hello");
        const events = parseLines(stream.lines);
        assert.strictEqual(events[0].component, "test");
        assert.strictEqual(events[0].service, "wouri-whatsapp");
    });
});
