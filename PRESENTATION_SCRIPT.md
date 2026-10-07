# BTMS (Battery Thermal Management System) — Presentation & Demo Script


Username / User ID: admin (or admin@btms.local)
Password: admin123

---
## INTRO & THE PROBLEM (1-2 Minutes)
**Speaker:**
"Hello everyone. Today I want to walk you through the BTMS—our Battery Thermal Management System. 

If you look at modern electric vehicles and grid energy storage, the single greatest point of failure—and the biggest safety risk—is thermal runaway. When a lithium-ion battery cell overheats, it can trigger a catastrophic chain reaction. But by the time a traditional temperature sensor triggers a 'high heat' alarm, the damage is already done. The internal chemistry is failing.

We realized that to solve this, we couldn't just monitor temperature. We had to *predict* failure and act *preemptively*. And we needed to build this system with an absolute, uncompromising focus on software quality and fault-tolerance, because in the energy sector, a software bug can literally cause a fire."

---
## THE SOLUTION & END-TO-END WORKFLOW (2-3 Minutes)
**Speaker:**
"Our solution is an AI-driven, microservices-based Digital Twin. Let me walk you through how it works end-to-end.

At the physical layer, we simulate a 10-cell cylindrical battery pack. Every second, our sensors pull telemetry: surface temperature, terminal voltage, charge/discharge current, and State of Charge (SoC).

**[Decision 1: Microservices Architecture]**
We decided to decouple our ingestion from our physics engine using a Redis message broker. 
*Why?* Because telemetry ingestion spikes shouldn't block critical physics calculations. By utilizing Flask for lightweight ingestion and FastAPI for the heavy AI inference, we ensure the system can scale horizontally and never drop a sensor reading.

**[Decision 2: The AI - Isolation Forest]**
This telemetry streams into our AI Engine. We chose an *Unsupervised Isolation Forest* for anomaly detection. 
*Why?* Because every battery degrades differently. We don't have historical labeled data for every possible failure mode. To achieve true predictive safety, the Isolation Forest continuously evaluates an 8-dimensional feature vector per cell: 
1. Surface temperature 
2. Terminal voltage 
3. Charge/Discharge current 
4. State of Charge (SoC) 
5. Normalized cell temperature 
6. Pack mean temperature 
7. Pack thermal spread (Max vs Min)
8. Individual cell deviation from the pack mean

By analyzing all 8 dimensions simultaneously, it isolates abnormal behavior—like a voltage sag relative to the pack average—*before* a catastrophic temperature spike ever occurs. It also retrains itself on the fly every 50 seconds to adapt to natural battery aging. 
*Performance-wise*, because Isolation Forests rely on computationally cheap algorithmic tree splits rather than heavy neural networks, it scores the entire battery pack in sub-millisecond execution times, never blocking the main event loop.

**[Decision 3: CFD Physics Engine]**
Once the AI detects an anomaly, it passes a severity score to our Computational Fluid Dynamics (CFD) engine. We don't just speed up a fan. We dynamically calculate the exact nanoparticle concentration (using Aluminum Oxide) and the exact required coolant flow velocity using the Graetz-Dittus-Boelter heat transfer equations. We actively dose the coolant to suppress the hotspot without wasting auxiliary pump energy."

---
## THE UI / DIGITAL TWIN (1 Minute)
**Speaker:**
"All of this is visualized in our React and Three.js frontend.
*Why WebGL/Three.js?* Because operators need spatial awareness. A 2D graph doesn't tell you *where* the heat is pooling. Our 3D interactive twin allows operators to visually trace thermal gradients in real-time. It’s secured behind a FastAPI Authentication layer using stateless JWTs and bcrypt hashing to ensure only authorized engineers can override coolant setpoints."

---
## QUALITY ASSURANCE & TESTING (3-4 Minutes) **[CORE FOCUS]**
**Speaker:**
"Now, none of this AI or physics matters if the software crashes. Because this is a mission-critical safety system, we didn't just write tests—we engineered an 8-layer Quality Assurance fortress. 

Let me break down our testing philosophy:

**1. Data-Driven & Keyword-Driven Testing (Legacy)**
First, we proved the ML heuristics across 185 parametric combinations and simulated business flows using keyword tables. We even built a synthetic data generator that validates the system against millions of edge-case telemetry rows.

**2. Unit & Functional Testing**
We used Pytest to mathematically validate our CFD equations. We assert that our Einstein viscosity calculations are perfectly accurate. We then test the APIs functionally using TestClients to ensure our auth flows and dev server endpoints never drop a connection.

**3. Security Testing (Custom + Wapiti)**
Security in infrastructure is non-negotiable. We wrote custom Python tests to actively try to spoof JWT tokens, attempt SQL injections, and bypass rate limits. Then, we integrated **Wapiti** for dynamic attack surface scanning to automatically flag things like missing CORS restrictions or exposed internal server versions.

**4. Performance & Load Testing**
FastAPI is fast, but we needed guarantees. We wrote microbenchmarks asserting that our CFD optimization function executes in under 1 millisecond. We then integrated **Locust** to simulate 50+ concurrent operator dashboards hammering the server, ensuring our p99 latency stays completely flat.

**5. Mutation Testing (The Ultimate QA)**
Finally, how do we know our tests are actually good? We used **mutmut** for Mutation Testing. The framework goes into our source code and intentionally introduces bugs—flipping a `>` to a `<`, or changing a `+` to a `-`. If our test suite *doesn't* fail, it means our tests are weak. I am proud to say we achieved a 100% kill rate on our critical mutation targets. 

**Conclusion on QA:**
By layering Unit, Functional, Security, Performance, and Mutation testing, we have mathematically and empirically proven that our AI will catch the thermal runaway, and our software will not fail when it does."

---
## CLOSING & IMPACT (1 Minute)
**Speaker:**
"To summarize: BTMS is not just a dashboard. It is a preemptive, self-learning safety mechanism. 
It saves energy by only heavily dosing coolant when mathematically necessary. 
It saves batteries by catching chemical degradation before thermal runaway. 
And it is built on a software foundation that has been aggressively mutated, load-tested, and security-scanned to guarantee enterprise-grade reliability.

Thank you. I’d love to show you the live dashboard or dive into the testing code."
