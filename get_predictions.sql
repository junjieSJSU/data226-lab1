SELECT symbol, date, forecast, lower_bound, upper_bound
FROM lab1.analytics.stock_data
WHERE forecast IS NOT NULL
ORDER BY symbol, date;