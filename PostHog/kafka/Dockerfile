FROM apache/kafka:3.9.2

# Single-broker KRaft mode (no separate Zookeeper container) -- right-sized for hobby-scale
# analytics traffic. bitnami/kafka was the original choice here but Bitnami pulled all pinned
# tags from Docker Hub's free tier in 2025 (only a paid Tanzu registry has them now) -- this is
# Apache's own official image instead, KRaft-native, no bitnami-specific KAFKA_CFG_ prefix. All
# listener config (KAFKA_*, CLUSTER_ID) is set as Railway variables on this service rather than
# baked in here, since KAFKA_ADVERTISED_LISTENERS needs this service's own Railway private
# domain -- see PostHog/README.md.
EXPOSE 9092
