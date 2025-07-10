# Temperature
SELECT
  ts AS "time",
  sensor,
  value
FROM telemetry
WHERE
  sensor LIKE '%temp%' AND
  ts >= $__timeFrom() AND ts <= $__timeTo()
ORDER BY ts ASC

# Pressure
SELECT
  ts AS "time",
  sensor,
  value
FROM telemetry
WHERE
  source = 'PLC' AND
  ts >= $__timeFrom() AND ts <= $__timeTo()
ORDER BY ts ASC

# Transformations
- multiframe time-series