import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider, createBrowserRouter } from 'react-router-dom'

import App from './App'
import './index.css'
import { BudgetPage } from './pages/Budget'
import { CategoriesPage } from './pages/Categories'
import { ImportHistoryPage } from './pages/ImportHistory'
import { ImportPage } from './pages/Import'
import { OverviewPage } from './pages/Overview'
import { RefundsPage } from './pages/Refunds'
import { ReportPage } from './pages/Report'
import { RulesPage } from './pages/Rules'
import { SavingsPage } from './pages/Savings'
import { SettingsPage } from './pages/Settings'
import { SubscriptionsPage } from './pages/Subscriptions'
import { TransactionsPage } from './pages/Transactions'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
})

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <OverviewPage /> },
      { path: 'transaktioner', element: <TransactionsPage /> },
      { path: 'import', element: <ImportPage /> },
      { path: 'import/historik', element: <ImportHistoryPage /> },
      { path: 'kategorier', element: <CategoriesPage /> },
      { path: 'regler', element: <RulesPage /> },
      { path: 'aterbetalningar', element: <RefundsPage /> },
      { path: 'prenumerationer', element: <SubscriptionsPage /> },
      { path: 'budget', element: <BudgetPage /> },
      { path: 'rapport', element: <ReportPage /> },
      { path: 'rapport/:month', element: <ReportPage /> },
      { path: 'sparande', element: <SavingsPage /> },
      { path: 'installningar', element: <SettingsPage /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
