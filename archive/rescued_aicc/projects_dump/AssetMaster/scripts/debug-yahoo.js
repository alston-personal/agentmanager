const yahooFinance = require('yahoo-finance2').default;

async function test() {
  try {
    const q = await yahooFinance.quote('AAPL');
    console.log('AAPL Quote:', JSON.stringify(q, null, 2));
  } catch (e) {
    console.error('AAPL Error:', e);
  }
}

test();
