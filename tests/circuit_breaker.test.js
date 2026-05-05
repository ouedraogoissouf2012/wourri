/**
 * Tests unitaires pour CircuitBreaker.
 * Exécution : node --test tests/circuit_breaker.test.js
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert");
const { CircuitBreaker, CircuitOpenError, STATE } = require("../lib/circuit_breaker");

const silentLogger = { log: () => {} };

describe("CircuitBreaker — état initial et transitions de base", () => {
    test("démarre en état CLOSED", () => {
        const breaker = new CircuitBreaker({ name: "t", logger: silentLogger });
        assert.strictEqual(breaker.state, STATE.CLOSED);
    });

    test("CLOSED : laisse passer les appels qui réussissent", async () => {
        const breaker = new CircuitBreaker({ name: "t", logger: silentLogger });
        const result = await breaker.execute(async () => "ok");
        assert.strictEqual(result, "ok");
        assert.strictEqual(breaker.state, STATE.CLOSED);
    });

    test("CLOSED : propage les erreurs de fn sans changer d'état (samples insuffisants)", async () => {
        const breaker = new CircuitBreaker({
            name: "t",
            windowSize: 10,
            logger: silentLogger,
        });
        await assert.rejects(
            () => breaker.execute(async () => { throw new Error("boom"); }),
            /boom/,
        );
        assert.strictEqual(breaker.state, STATE.CLOSED);
    });

    test("reset() force le retour en CLOSED", async () => {
        const breaker = new CircuitBreaker({
            name: "t",
            windowSize: 2,
            failureThreshold: 0.5,
            logger: silentLogger,
        });
        for (let i = 0; i < 2; i++) {
            try { await breaker.execute(async () => { throw new Error("x"); }); } catch (_) {}
        }
        assert.strictEqual(breaker.state, STATE.OPEN);
        breaker.reset();
        assert.strictEqual(breaker.state, STATE.CLOSED);
    });
});

describe("CircuitBreaker — ouverture sur seuil d'erreurs", () => {
    test("CLOSED → OPEN quand ratio failures >= seuil sur fenêtre pleine", async () => {
        const breaker = new CircuitBreaker({
            name: "t",
            windowSize: 4,
            failureThreshold: 0.5,
            logger: silentLogger,
        });
        for (let i = 0; i < 4; i++) {
            try { await breaker.execute(async () => { throw new Error("x"); }); } catch (_) {}
        }
        assert.strictEqual(breaker.state, STATE.OPEN);
    });

    test("CLOSED reste CLOSED si la fenêtre n'est pas pleine", async () => {
        const breaker = new CircuitBreaker({
            name: "t",
            windowSize: 10,
            failureThreshold: 0.5,
            logger: silentLogger,
        });
        for (let i = 0; i < 4; i++) {
            try { await breaker.execute(async () => { throw new Error("x"); }); } catch (_) {}
        }
        assert.strictEqual(breaker.state, STATE.CLOSED);
    });

    test("CLOSED reste CLOSED si ratio failures < seuil sur fenêtre pleine", async () => {
        const breaker = new CircuitBreaker({
            name: "t",
            windowSize: 4,
            failureThreshold: 0.75,
            logger: silentLogger,
        });
        // 2 failures + 2 successes = ratio 0.5 < 0.75 → CLOSED
        for (let i = 0; i < 2; i++) {
            try { await breaker.execute(async () => { throw new Error("x"); }); } catch (_) {}
        }
        for (let i = 0; i < 2; i++) {
            await breaker.execute(async () => "ok");
        }
        assert.strictEqual(breaker.state, STATE.CLOSED);
    });

    test("ring buffer : succès récents font sortir les anciens échecs de la fenêtre", async () => {
        const breaker = new CircuitBreaker({
            name: "t",
            windowSize: 4,
            failureThreshold: 0.75,
            logger: silentLogger,
        });
        // 3 failures + 4 successes : seules les 4 dernières comptent → 4 successes → OK
        for (let i = 0; i < 3; i++) {
            try { await breaker.execute(async () => { throw new Error("x"); }); } catch (_) {}
        }
        for (let i = 0; i < 4; i++) {
            await breaker.execute(async () => "ok");
        }
        assert.strictEqual(breaker.state, STATE.CLOSED);
    });
});

describe("CircuitBreaker — comportement OPEN", () => {
    function makeOpen(extra = {}) {
        const breaker = new CircuitBreaker({
            name: "t",
            windowSize: 2,
            failureThreshold: 0.5,
            openDurationMs: 5000,
            logger: silentLogger,
            ...extra,
        });
        return breaker;
    }

    test("OPEN : jette CircuitOpenError sans appeler fn", async () => {
        const breaker = makeOpen();
        for (let i = 0; i < 2; i++) {
            try { await breaker.execute(async () => { throw new Error("x"); }); } catch (_) {}
        }
        assert.strictEqual(breaker.state, STATE.OPEN);
        let called = false;
        await assert.rejects(
            () => breaker.execute(async () => { called = true; return "ok"; }),
            CircuitOpenError,
        );
        assert.strictEqual(called, false);
    });

    test("CircuitOpenError contient le nom du circuit", async () => {
        const breaker = makeOpen({ name: "wouri-api" });
        for (let i = 0; i < 2; i++) {
            try { await breaker.execute(async () => { throw new Error("x"); }); } catch (_) {}
        }
        try {
            await breaker.execute(async () => "ok");
            assert.fail("should have thrown");
        } catch (err) {
            assert.ok(err instanceof CircuitOpenError);
            assert.strictEqual(err.circuitName, "wouri-api");
        }
    });
});

describe("CircuitBreaker — transition OPEN → HALF_OPEN → CLOSED/OPEN", () => {
    test("OPEN → HALF_OPEN après openDurationMs, puis CLOSED si succès", async () => {
        let now = 1000;
        const breaker = new CircuitBreaker({
            name: "t",
            windowSize: 2,
            failureThreshold: 0.5,
            openDurationMs: 5000,
            now: () => now,
            logger: silentLogger,
        });
        for (let i = 0; i < 2; i++) {
            try { await breaker.execute(async () => { throw new Error("x"); }); } catch (_) {}
        }
        assert.strictEqual(breaker.state, STATE.OPEN);

        now += 6000; // dépasse openDurationMs
        const result = await breaker.execute(async () => "sentinel-ok");
        assert.strictEqual(result, "sentinel-ok");
        assert.strictEqual(breaker.state, STATE.CLOSED);
    });

    test("HALF_OPEN sentinelle échoue → retour en OPEN", async () => {
        let now = 1000;
        const breaker = new CircuitBreaker({
            name: "t",
            windowSize: 2,
            failureThreshold: 0.5,
            openDurationMs: 5000,
            now: () => now,
            logger: silentLogger,
        });
        for (let i = 0; i < 2; i++) {
            try { await breaker.execute(async () => { throw new Error("x"); }); } catch (_) {}
        }
        now += 6000;
        try {
            await breaker.execute(async () => { throw new Error("still failing"); });
        } catch (_) {}
        assert.strictEqual(breaker.state, STATE.OPEN);
    });

    test("HALF_OPEN: les appels concurrents au-delà de halfOpenMaxCalls sont rejetés", async () => {
        let now = 1000;
        const breaker = new CircuitBreaker({
            name: "t",
            windowSize: 2,
            failureThreshold: 0.5,
            openDurationMs: 5000,
            halfOpenMaxCalls: 1,
            now: () => now,
            logger: silentLogger,
        });
        for (let i = 0; i < 2; i++) {
            try { await breaker.execute(async () => { throw new Error("x"); }); } catch (_) {}
        }
        now += 6000;

        // Lancer 3 sentinelles "lentes" en parallèle, seule la première doit passer
        let resolveSentinel;
        const sentinelPromise = new Promise((resolve) => { resolveSentinel = resolve; });
        const p1 = breaker.execute(async () => sentinelPromise);
        const p2 = breaker.execute(async () => "should-not-run").then(
            () => "ran",
            (err) => err,
        );
        const p3 = breaker.execute(async () => "should-not-run").then(
            () => "ran",
            (err) => err,
        );

        const r2 = await p2;
        const r3 = await p3;
        assert.ok(r2 instanceof CircuitOpenError, "p2 doit être rejeté");
        assert.ok(r3 instanceof CircuitOpenError, "p3 doit être rejeté");

        resolveSentinel("sentinel-ok");
        const r1 = await p1;
        assert.strictEqual(r1, "sentinel-ok");
        assert.strictEqual(breaker.state, STATE.CLOSED);
    });
});

describe("CircuitBreaker — stats", () => {
    test("stats reflète les samples et le ratio courant", async () => {
        const breaker = new CircuitBreaker({
            name: "t",
            windowSize: 4,
            failureThreshold: 0.75,
            logger: silentLogger,
        });
        await breaker.execute(async () => "ok");
        await breaker.execute(async () => "ok");
        try { await breaker.execute(async () => { throw new Error("x"); }); } catch (_) {}

        const s = breaker.stats;
        assert.strictEqual(s.state, STATE.CLOSED);
        assert.strictEqual(s.samples, 3);
        assert.strictEqual(s.successes, 2);
        assert.strictEqual(s.failures, 1);
        assert.ok(Math.abs(s.failureRatio - 1 / 3) < 1e-9);
    });
});
