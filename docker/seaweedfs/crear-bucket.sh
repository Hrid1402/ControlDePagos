for i in $(seq 1 30); do
  if docker compose exec -T seaweedfs sh -c 'echo "s3.bucket.list" | weed shell' >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker compose exec -T seaweedfs sh -c 'echo "s3.bucket.create -name control-pagos" | weed shell' >/dev/null 2>&1 || true
echo "Bucket control-pagos listo"
