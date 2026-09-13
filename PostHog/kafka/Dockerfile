FROM bitnami/kafka:3.7

# Single-broker KRaft mode (no separate Zookeeper container) -- right-sized for hobby-scale
# analytics traffic. All KRaft/listener config (KAFKA_CFG_*, KAFKA_KRAFT_CLUSTER_ID) is set as
# Railway variables on this service rather than baked in here, since KAFKA_CFG_ADVERTISED_LISTENERS
# needs this service's own Railway private domain -- see PostHog/README.md.
EXPOSE 9092
