#!/usr/bin/env python3
"""Local protocol fixture; never connects to OpenAI."""
import asyncio
import json
import sys

threads, turns = {}, {}

def emit(message):
    print(json.dumps(message), flush=True)

def notify(method, thread_id, turn_id, **fields):
    emit({'method': method, 'params': {'threadId': thread_id, 'turnId': turn_id, **fields}})

async def answer(thread, turn, prompt):
    try:
        notify('item/agentMessage/delta', thread, turn, itemId='message', delta='323')
        if 'SLOW' in prompt:
            await asyncio.sleep(30)
        else:
            await asyncio.sleep(.01)
        notify('item/completed', thread, turn, item={'type':'agentMessage','text':'323','phase':'final_answer'})
        notify('thread/tokenUsage/updated', thread, turn, tokenUsage={'last':{'inputTokens':100,'outputTokens':5,'cachedInputTokens':20}})
        notify('turn/completed', thread, turn, turn={'id':turn,'status':'completed','durationMs':10})
    except asyncio.CancelledError:
        notify('turn/completed', thread, turn, turn={'id':turn,'status':'interrupted'})

async def main():
    while line := await asyncio.to_thread(sys.stdin.readline):
        request=json.loads(line)
        if 'id' not in request:
            continue
        method, params, identifier=request['method'],request['params'],request['id']
        if method=='initialize':result={}
        elif method=='account/read':result={'account':{'type':'chatgpt'}}
        elif method=='thread/start':
            thread=f'thread-{len(threads)}';threads[thread]=params
            result={'thread':{'id':thread},'model':params['model'],'serviceTier':params['serviceTier']}
        elif method=='turn/start':
            thread=params['threadId'];turn=f'turn-{identifier}'
            result={'turn':{'id':turn}}
            turns[turn]=asyncio.create_task(answer(thread,turn,params['input'][0]['text']))
        elif method=='turn/interrupt':
            turns[params['turnId']].cancel();result={}
        elif method=='thread/unsubscribe':result={}
        else:
            emit({'id':identifier,'error':{'code':-32601,'message':'Unknown method'}});continue
        emit({'id':identifier,'result':result})

asyncio.run(main())
