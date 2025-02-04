const express = require('express')
const app = express()
const port = process.env.PORT || 8081

app.use(express.json())

// Global key/value store
let stor = Object({})

app.get('/data', (req, res) =>{
  res.status(200).set("Content-Type", "application/json").send(stor)
})

app.get('/data/:key', (req, res) => {
  let key = req.params.key

  // Case 1: Key found, returning associated value in dictionary
  if (stor[key]){
    console.log("HTTP/1.1 200 OK ", key, stor[key])
    res.status(200).send({"value": stor[key]})
  }
  // Case 2: STATUS 404, Not found
  else if(!stor[key]){
    console.log("HTTP1.1 404 Not Found")
    res.status(404).send({error: "Key not found!"})
  }
})

app.put('/data/:key', (req, res) => {
  // note: key is allowed to go in urls
  // possible case: can there be multiple keys in a request?
  let key = req.params.key
  // let values = Object.values(req.body)
  
  // Case 1: STATUS 400, Request body or Key does not exist
  if (!req.body || !req.body.value){
    console.log("HTTP/1.1 400 Bad Request")
    res.status(400).send("Request body or key not found")
    return 0
  }
  // Case 2: STATUS 201, Key is not inside storage, adding new key
  if (!stor[key]){
    stor[key] = req.body.value
    console.log("HTTP/1.1 201 Created ", key, stor[key])
    res.status(201).send("Created Key/Value pair:")
  }
  // Case 3: STATUS 200, Updating existing key
  else{
    stor[key] = req.body.value
    console.log("HTTP/1.1 200 OK ", key, stor[key])
    res.status(200).send("Updated Key/Value pair")
  }
})

app.delete('/data/:key', (req, res) => {
  let key = req.params.key

  // Case 2: STATUS 404, Key not found for deletion
  if (!req.body || !req.params || !key || !stor[key]){
    console.log("HTTP/1.1 404 Not Found, Key deletion unsuccessful")
    res.status(404).send("Key deletion not successful; not found in key/value store")
    return 0
  }

  // Case 1: STATUS 200, Key exists 
  if (stor[key]){
    delete stor[key]
    console.log("HTTP/1.1 200 OK, Deleted key: ", key)
    res.status(200).send("Key deletion successful")
  }
})

app.listen(port, () => {
  console.log(`CSE 138 Assignment 1: HTTP Server listening on port ${port}`)
})