---
tags:
  - IT
  - 000_コンピュータ科学・情報・総記
  - 読書感想文
publish: true
---
このチュートリアルを読んでメモをする。
https://nextjs.org/learn/foundations/about-nextjs

# 2023-07-14-Nextjs

https://nextjs.org/learn/foundations/about-nextjs/what-is-nextjs
モダンアプリケーションを作るときに考えなきゃいけないこと。
　User Interface
　Routing
　Data Fetching
 Rendering これはおやっと思ったけど、SSRとかを意識した話か
 Integrations これは業務システム出身なので思いつかなくてなるほどと思った
 Infrastructure
 Performance
 Scalability
 Developer Experience
ReactとはUIのためのライブラリ
Next.jsはReactのフレームワーク

[* From JavaScript to React]
https://nextjs.org/learn/foundations/from-javascript-to-react
ここからDOMの話でちょっと飛ばす。

https://nextjs.org/learn/foundations/from-javascript-to-react/getting-started-with-react
reactとreact-domが必要
JSXはJavascriptの拡張構文。HTMLのような記述でUIを表現することができる。
JSXの3つのルールに従うことで、新しく何かを覚える必要がなくなるー＞XAMLは負けるよな
 単一のルートの要素を返す
 タグは全部閉じる
 ほとんどをキャメルケースにする（変数にすることができる）

ブラウザはJSXを読めないので、BabelのようなJSコンパイラを入れる。
scriptのタイプを\<script type="text/jsx"\> と記述して、Babelにこれが何か伝える。

declarative 宣言的なReactのコードと、imperative 命令的な VanillaJSのコード
命令的というのはプロセスを書いているけど結果が分からない。
宣言的は結果がこうなるというのを明示的にしている、ということか？

次回はここから
https://nextjs.org/learn/foundations/from-javascript-to-react/essential-javascript-react

# 2023-07-15
今日はここから
https://nextjs.org/learn/foundations/from-javascript-to-react/essential-javascript-react
Javascriptについて
　ternary operator 三項演算子
　destructuring assignment 分割代入
　　この分割代入は時々importで見るやつな気がする。

https://nextjs.org/learn/foundations/from-javascript-to-react/react-core-concepts
[* React Core Concepts]
Reactの主要な概念が3つ
　Components
　Props
　State

https://nextjs.org/learn/foundations/from-javascript-to-react/building-ui-with-components
Componentsは画面を組み立てる部品。

https://nextjs.org/learn/foundations/from-javascript-to-react/displaying-data-with-props
[* Displaying Data with Props]
プロパティとしてちょっとした情報をReactのコンポーネントに渡すことができる。これをpropsと呼ぶ。
引数を受け取るcomponentsを設計することもできるし、わたってきた引数propsを子どものComponentsに渡すこともできる。

JSXの中では波カッコで変数を使用したり、String Format的なのをすることができる。
array.map() を使って、繰り返しの処理をすることもできる。

次はここから
https://nextjs.org/learn/foundations/from-javascript-to-react/adding-interactivity-with-state

# 2023-07-18
https://nextjs.org/learn/foundations/from-javascript-to-react/adding-interactivity-with-state
StateとEvent Handlerをつかってどうやってインタラクティブさを実現できるか見ていく。
状態を管理するためのReact hookはuseState() と呼ばれるものです。
これを呼ぶと配列が返され、分割代入でアクセスできる。

1つ目の要素は値、2つ目の要素は値を更新するためのメソッド。

なんかこのuseStateは多用するなみたいのをどこかで読んだ気がする。
これか。
https://zenn.dev/mocomichi/articles/47c95425bc28d5

続きはまた明日。

# 2023-07-19
[[2023-07-19-Nextjs]]
[[2023-07-21-Nextjs]]
[[2023-07-24-Nextjs]]
[[2023-07-30-Nextjs]]
[[2023-08-02-Nextjs]]
[[2023-08-09-Nextjs]]
