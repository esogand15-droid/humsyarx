import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { ROUTER_BASENAME } from './lib/base';
import './styles/globals.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

/* 🚂 Railway: باندل زیر /app/ سرو می‌شود، پس router هم باید همان
   base را بداند. مقدار از تک‌منبع حقیقت src/lib/base.js خوانده
   می‌شود و در حالت ریشه undefined است (رفتار قبلی دست‌نخورده). */
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter basename={ROUTER_BASENAME}>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </BrowserRouter>
  </React.StrictMode>
);
