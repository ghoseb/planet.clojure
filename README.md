Planet Clojure
==============

This is the source code of [Planet Clojure](http://planet.clojure.in).

Planet Clojure runs on [Venus](http://intertwingly.net/code/venus/) which is
written in [Python](http://python.org/) (a *fine* programming language).

The template of Planet Clojure was designed by
[Brajeshwar](http://brajeshwar.com); so all credit goes to him.


Adding yourself to Planet Clojure
---------------------------------

If you have a blog on Clojure and want to feature on Planet Clojure,
fork this project on Github, edit the file `clojure/config.ini` and
add your blog feed URL and your name in the following format - 

    [http://path/to/your/blog/feed/]
    name = Your Name

After you are done, commit the change to your repository and send me a
pull request. I will be happy to add you to Planet Clojure.

Note: Please add the feed which contains only those posts which are 
Clojure/Lisp related. 

As a policy we do not put generic feeds on Planet Clojure, but if you don't have
Clojure-specific feed on your site, you may try to add following parameter to the section
to filter only Clojure-specific posts (but be careful, it may not be very precise if your
feed doesn't include enough text to match this regex):

    filter = (clojure|Clojure|\(def |\(defn-? )

If you also have Twitter account, please add `twitter` parameter to the section, like
this:

    twitter = <handle-without-@>


Reporting Bugs
--------------

If you have an issue with the design or even Planet, feel free to send
me pull requests of your fixes. I will be happy to  merge those into
my tree.
