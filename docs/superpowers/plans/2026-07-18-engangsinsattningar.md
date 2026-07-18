# Plan: engångsinsättningar

Spec: [../specs/2026-07-18-engangsinsattningar-design.md](../specs/2026-07-18-engangsinsattningar-design.md)

## Steg

1. **Migration + modell** — `007_savings_deposits.sql`, `SavingsDeposit` i
   `models.py`.
2. **Tester först (RED)** — `backend/app/tests/test_savings_deposits.py`:
   beräkningslogik, plan-summary, history, API-validering, kaskad,
   användarscenariot ur kontoutdraget.
3. **Beräkningslogik (GREEN)** — `savings_plan.py`: `_oneoffs_until`,
   deposits-parameter i `invested_at`/`_baseline`, första start = min(plan,
   insättning), `invested_series` över planer ∪ insättningar, `plan_summary`
   skickar med insättningar.
4. **API** — `routers/savings.py`: GET/POST
   `/savings/accounts/{id}/deposits`, DELETE `/savings/deposits/{id}`.
5. **Frontend** — `SavingsDeposit`-typ, `useDeposits`-hook, ny
   `DepositsDialog.tsx` under `components/savings/`, knapp "Insättningar" i
   `Savings.tsx`.
6. **Verifiering** — `pytest` (hela sviten), `npm run build` (typecheck),
   kodgranskning, commit.
