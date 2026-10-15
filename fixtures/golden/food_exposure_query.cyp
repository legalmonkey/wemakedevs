MATCH (u {id: $unit_id})-[:SHIPS_IN]->(s)-[:DELIVERED_TO]->(r) RETURN u.id AS unit_id, s.id AS shipment_id, r.id AS recipient_id, s.status AS status, properties(r) AS recipient_properties
