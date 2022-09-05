### Build

```bash
forge build --root .
```

### Deploy

```deploy
forge create Arbitrageur4 \
    --root . \
    --rpc-url=$RPC_URL \
    --private-key=$PRIVATE_KEY \
    --constructor-args "$HUB_ADDRESS" "$UNI_V2_FACTORY_ADDRESS" "$OWNER_ADDRESS" "$EXECUTOR_ADDRESS"
```
