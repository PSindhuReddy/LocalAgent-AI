from events import bus
from orchestrator import Orchestrator

bus.subscribe(lambda e: print(f"  [{e['agent']:<10}] {e['status']:<8} {e['detail']}"))

if __name__ == "__main__":
    o = Orchestrator()
    print("LocalAgent AI (Phase 1). Type 'exit' to quit.")
    while (q := input("\nAsk> ").strip()) not in ("exit", "quit"):
        for r in o.run(q)["results"]:
            print(f"\n- {r['ref']} (score {r['score']:.2f})\n  {r['text'][:200]}...")