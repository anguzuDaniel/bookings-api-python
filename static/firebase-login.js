'use strict'

import { initializeApp } from 'https://www.gstatic.com/firebasejs/9.22.2/firebase-app.js'
import { getAuth, createUserWithEmailAndPassword, signInWithEmailAndPassword, signOut } from 'https://www.gstatic.com/firebasejs/9.22.2/firebase-auth.js'

  // Your web app's Firebase configuration
  // For Firebase JS SDK v7.20.0 and later, measurementId is optional
  const firebaseConfig = {
    apiKey: "AIzaSyA-RdOAeAAzyay_eJjzwRLJ6Xmn3Z-icqQ",
    authDomain: "pyton-fastapi-example.firebaseapp.com",
    projectId: "pyton-fastapi-example",
    storageBucket: "pyton-fastapi-example.appspot.com",
    messagingSenderId: "750013802649",
    appId: "1:750013802649:web:5249b9e9f22f7973203008",
    measurementId: "G-YYJ19L47NM"
  };

window.addEventListener('load', function() {
    const app = initializeApp(firebaseConfig)
    const auth = getAuth(app)
    updateUI(document.cookie)
    console.log("Hello world load")

    document.getElementById('sign-up').addEventListener('click', function() {
        const email = document.getElementById('email').value
        const password = document.getElementById('password').value

        createUserWithEmailAndPassword(auth, email, password)
        .then((userCredential) => {
            const user = userCredential.user;

            user.getIdToken().then((token) => {
                document.cookie = "token=" + token + ";path=/;SameSite=Strict";
                window.location = "/";
            }) 
        }) 
        .catch((error) => {
            console.log(error.code + error.message)
        })
    })

    // login of the user to firebase
    document.getElementById('login').addEventListener('click', function() {
        const email = document.getElementById('email').value
        const password = document.getElementById('password').value

        signInWithEmailAndPassword(auth, email, password)
        .then((userCredential) => {
            const user = userCredential.user
            console.log('Logged in')

            user.getIdToken().then((token) => {
                document.cookie = "token=" + token + ";path=/;SameSite=Strict"
                window.location = "/"
            })
        })
        .catch((error) => {
            console.log(error.code + error.message);
        })
    })

    document.getElementById('sign-out').addEventListener('click', function() {
        signOut(auth)
        .then((output) => {
            document.cookie = "token=;path=/;SameSite=Strict";
            window.location = "/";
        })
    })
})


function updateUI(cookie) {
    var token = parseCookieToken(cookie)

    if (token.length > 0) {
        document.getElementById('login-box').hidden = true
        document.getElementById('sign-out').hidden = false
    } else {
        document.getElementById('login-box').hidden = false
        document.getElementById('sign-out').hidden = true
    }
}

function parseCookieToken(cookie) {
    var strings = cookie.split(';')

    for (let i = 0; i < strings.length; i++) {
        var temp = strings[i].split('=')

        if(temp[0] == "token")
            return temp[1]
    }

    return ""
}